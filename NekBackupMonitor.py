#!/usr/bin/python3

import argparse;
import sqlite3;
import datetime;
import time;
import sys;
import os;
import configparser;
from enum import Enum;
from email.mime.text import MIMEText;
from email.mime.multipart import MIMEMultipart;
from subprocess import Popen, PIPE;
from croniter import croniter;
from urllib.request import pathname2url;
from pprint import pprint;
import shutil;

class NekBackupMonitor(object):

  currentPath = os.path.dirname(os.path.abspath(__file__));
  sqlite_file = currentPath + '/NekBackupMonitor.db';
  tableSchedules = 'schedules';
  tableReports = 'reports';
  settings_file = currentPath + '/settings.conf';

  # read configuration file

  config = configparser.ConfigParser()

  if(os.path.exists(settings_file) == False):
    print("ERROR: settings file settings.conf does not exist", file=sys.stderr);
    exit(2);

  config.read(settings_file);
  
  if(not 'General' in config):
    print("ERROR: settings file does not contain a [General] section", file=sys.stderr);
    exit(3);

  if(not 'ToEmail' in config['General']):
    print("ERROR: The settings file does not contain a ToEmail setting under the [General] section", file=sys.stderr);
    exit(3);
  if(not 'FromEmail' in config['General']):
    print("ERROR: The settings file does not contain a FromEmail setting under the [General] section", file=sys.stderr);
    exit(3);

  toEmail = config['General']['ToEmail'];
  fromEmail = config['General']['FromEmail']

  if(not toEmail):
    print("ERROR: The ToEmail setting is empty", file=sys.stderr);
    exit(3);
  if(not fromEmail):
    print("ERROR: The FromEmail setting is empty", file=sys.stderr);
    exit(3);

  NOTIFY_OK = 1;
  NOTIFY_ERROR = 2;

  # check if sendmail exists
  sendmail = shutil.which("sendmail");
  if sendmail == None:
    print("ERROR: sendmail does not exist", file=sys.stderr);
    exit(2);

  # Connecting to the database file

  # check if db file exists
  try:
    dburi = 'file:{}?mode=rw'.format(pathname2url(sqlite_file));
    conn = sqlite3.connect(dburi, uri=True);
  except sqlite3.OperationalError:
    # db doesn't exist. create the schema
    conn = sqlite3.connect(sqlite_file);
    conn.execute("""
      CREATE TABLE IF NOT EXISTS "Schedules" (
          "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
          "Title" TEXT NOT NULL,
          "Interval" INTEGER NOT NULL DEFAULT (1),
          "SourceHost" TEXT NOT NULL,
          "DestinationHost" TEXT NOT NULL,
          "SourceDir" TEXT NOT NULL,
          "DestinationDir" TEXT NOT NULL,
          "Type" INTEGER NOT NULL
      );
    """);
    conn.execute("""
      CREATE TABLE reports (
          "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
          "Schedule" INTEGER NOT NULL,
          "date" INTEGER NOT NULL,
          "Result" INTEGER NOT NULL,
          "message" TEXT,
          "duration" INTEGER
      );
    """);

  conn.row_factory = sqlite3.Row;

  def __init__(self):

    parser = argparse.ArgumentParser(prog='nekbackupmonitor.py');

    p_report = argparse.ArgumentParser(add_help=False);
    p_report.add_argument('-s', '--schedule-id', type=int, help='the Schedule ID of the running task');
    p_report.add_argument('-t', '--starting-timestamp', type=str, help='the UNIX timestamp of the start of the task run');
    p_report.add_argument('-r', '--result', choices=['done', 'done-and-verified', 'done-but-verify-error', 'failed'], help='the result of the task run');
    p_report.add_argument('-d', '--duration-in-seconds', type=float, help='(optional) the duration of the running task in seconds');
    p_report.add_argument('-m', '--message', help='A detailed message (e.g. output log) associated with the running of the task.');
    p_report.add_argument('--stdin-message', action="store_true", help='Read the associated detailed message from the stdin. For messages that exceed 1000 chars use this method, instead of the -m option above.');

    p_delete_report = argparse.ArgumentParser(add_help=False);
    p_delete_report.add_argument('ID', type=int, help='report ID');

    p_add_schedule = argparse.ArgumentParser(add_help=False);
    p_add_schedule.add_argument('TITLE', type=str, help='schedule title');
    p_add_schedule.add_argument('INTERVAL', type=str, help='schedule interval in cron format');
    p_add_schedule.add_argument('SOURCE_HOST', type=str, help='schedule source host');
    p_add_schedule.add_argument('DESTINATION_HOST', type=str, help='schedule destination host');
    p_add_schedule.add_argument('SOURCE_DIR', type=str, help='schedule source dir');
    p_add_schedule.add_argument('DESTINATION_DIR', type=str, help='schedule destination dir');
    p_add_schedule.add_argument('TYPE', type=int, help='schedule type');

    p_delete_schedule = argparse.ArgumentParser(add_help=False);
    p_delete_schedule.add_argument('ID', type=int, help='schedule ID');

    p_check = argparse.ArgumentParser(add_help=False);
    p_check.add_argument('-d', '--date', type=str, help='Date. The format is YYYY-mm-dd (e.g. 2015-03-16)');
    p_check.add_argument('-m', '--email', action="store_true", help='Also email the report.');
    p_check.add_argument('-b', '--days', type=str, help='Number of days prior. Do a check for the date that is that many days prior.');

    p_schedules = argparse.ArgumentParser(add_help=False);
    p_schedules.add_argument('-f', '--full', action="store_true", help='List with full details.');

    p_reports = argparse.ArgumentParser(add_help=False);
    p_reports.add_argument('-s', '--schedule', type=int, help='ID of schedule. List reports specifically for a schedule.');
    p_reports.add_argument('-r', '--report', type=int, help='ID of report. List details about a specific report.');
    p_reports.add_argument('-d', '--date', type=str, help='Date. List reports for a specific date. The format is YYYY-mm-dd (e.g. 2015-03-16)');
    p_reports.add_argument('-f', '--fromdate', type=str, help='From Date. List reports from a specific date. The format is YYYY-mm-dd (e.g. 2015-03-16)');
    p_reports.add_argument('-t', '--todate', type=str, help='To Date. List reports up until a specific date. The format is YYYY-mm-dd (e.g. 2015-03-16)');
    p_reports.add_argument('-b', '--days', type=str, help='Number of days. List reports up from that amount of days.');

    sp = parser.add_subparsers();
    sp_list_schedules = sp.add_parser('list-schedules', parents=[p_schedules], help='Lists schedules by default from 7 days prior');
    sp_list_schedules.set_defaults(which='list-schedules');

    sp_list_reports = sp.add_parser('list-reports', parents=[p_reports], help='Lists reports');
    sp_list_reports.set_defaults(which='list-reports');

    sp_check = sp.add_parser('check', parents=[p_check], help='Check reports');
    sp_check.set_defaults(which='check');

    sp_add = sp.add_parser('add', parents=[p_report], help='Add backup report');
    sp_add.set_defaults(which='add');

    sp_delete_schedule = sp.add_parser('delete-report', parents=[p_delete_schedule], help='Delete Report');
    sp_delete_schedule.set_defaults(which='delete-report');

    sp_add_schedule = sp.add_parser('add-schedule', parents=[p_add_schedule], help='Add Schedule');
    sp_add_schedule.set_defaults(which='add-schedule');

    sp_delete_schedule = sp.add_parser('delete-schedule', parents=[p_delete_schedule], help='Delete Schedule');
    sp_delete_schedule.set_defaults(which='delete-schedule');

    if(len(sys.argv)) == 1:
      parser.print_usage();
      exit(0);

    args = parser.parse_args();
    if(args.which == 'list-schedules'):
      self.listSchedules(args);
    elif(args.which == 'list-reports'):
      self.listReports(args);
    elif(args.which == 'add'):
      self.addReport(args);
    elif(args.which == 'delete-report'):
      self.deleteReport(args);
    elif(args.which == 'add-schedule'):
      self.addSchedule(args);
    elif(args.which == 'delete-schedule'):
      self.deleteSchedule(args);
    elif(args.which == 'check'):
      self.checkReports(args);

  def listSchedules(self, args):
    print("Listing Schedules");
    
    all_rows = self.getAllSchedules();
    
    if(args.full):
      templateColumns = "{index:4.4} {id:4.4} {title:15.15} {interval:>12.12} {sourcehost:10.10} {destinationhost:20.20} {sourcedir:30.30} {destinationdir:30.30} {type:2.2}";
      reportHeader = templateColumns.format(index="#", id="ID", title="Title", 
                        interval="Interval", sourcehost="SourceHost", 
                        destinationhost="DestinationHost", 
                        sourcedir="SourceDir", destinationdir="DestinationDir", 
                        type="Type");
      print(reportHeader);
      index = 0;
      for row in all_rows:
        index = index + 1;
        reportRow = templateColumns.format(index=str(index), id=str(row['id']), 
                        title=str(row['title']), interval=str(row['interval']), 
                        sourcehost=str(row['sourcehost']), 
                        destinationhost=str(row['destinationhost']),
                        sourcedir=str(row['sourcedir']),
                        destinationdir=str(row['destinationdir']),
                        type=str(row['type']));
        print(self.formatForTextDisplay(reportRow));
    else:
      templateColumns = "{index:4.4} {id:4.4} {title:15.15} {interval:>12.12} {sourcehost:15.15} {destinationhost:15.15}";
      reportHeader = templateColumns.format(index="#", id="ID", title="Title", 
                        interval="Interval", sourcehost="SourceHost", 
                        destinationhost="DestHost");
      print(reportHeader);
      index = 0;
      for row in all_rows:
        index = index + 1;
        reportRow = templateColumns.format(index=str(index), id=str(row['id']), 
                        title=str(row['title']), interval=str(row['interval']), 
                        sourcehost=str(row['sourcehost']), 
                        destinationhost=str(row['destinationhost']));
        print(self.formatForTextDisplay(reportRow));
    
  def listReports(self, args):
    c = self.conn.cursor();
    
    if(args.report):
      self.displayReport(args.report);
      return;
    
    if(args.schedule):
      selectedSchedule = self.getSchedule(args.schedule);
      if(selectedSchedule):
        print("Listing Reports for schedule " + selectedSchedule['title'] + " (ID: " + str(selectedSchedule['id']) + ")");
        c.execute('SELECT id, Schedule, date, Result, duration, message FROM {tn} WHERE schedule = :si'.format(tn=self.tableReports), {'si':args.schedule});
      else:
        print("ERROR: No schedule found with id: " + str(args.schedule), file=sys.stderr);
        exit(1);
    else:
      if(args.date or args.todate or args.fromdate):
        if(args.date):
          listReportsFromDate = self.parseDate(args.date);
          listReportsFromDate = listReportsFromDate.replace(hour=0, minute=0, second=0, microsecond=0);
          listReportsToDate = listReportsFromDate.replace(hour=23, minute=59, second=59, microsecond=999999);
        else:
          if(args.todate):
            listReportsToDate = self.parseDate(args.todate);
            listReportsToDate = listReportsToDate.replace(hour=23, minute=59, second=59, microsecond=999999);
          else:
            listReportsToDate = datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999);
          if(args.fromdate):
            listReportsFromDate = self.parseDate(args.fromdate);
          else:
            listReportsFromDate = datetime.datetime.min;
            listReportsFromDate = listReportsFromDate.replace(year=1900);
      else:
        if(args.days):
          try:
            numberOfdaysListReports = int(args.days)
          except ValueError:
            print("ERROR: Number of Days must be an positve integer e.g. 5 or 120", file=sys.stderr)
            exit(1);
          if(numberOfdaysListReports > 0 and numberOfdaysListReports < 40000):
            listReportsFromDate = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0);
            listReportsFromDate = listReportsFromDate - datetime.timedelta(days=numberOfdaysListReports);
            listReportsToDate = datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999);
          else:
            print("ERROR: Number of Days must be an positve integer e.g. 5 or 120", file=sys.stderr)
            exit(1);
        else:
          listReportsFromDate = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0);
          listReportsFromDate = listReportsFromDate - datetime.timedelta(days=7);
          listReportsToDate = datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999);
        
      if(listReportsToDate < listReportsFromDate):
        print("ERROR: To Date must be after the From Date.", file=sys.stderr);
        exit(1);
      d1 = listReportsFromDate;
      d2 = listReportsToDate;
      #d2 = d1 + datetime.timedelta(days=1);
      d1Timestamp = self.totimestamp(d1);
      d2Timestamp = self.totimestamp(d2);
      print("Listing Reports from date {d1} to {d2}".format(d1=listReportsFromDate.strftime("%Y-%m-%d %H:%M:%S"), d2=listReportsToDate.strftime("%Y-%m-%d %H:%M:%S")));
      queryString = 'SELECT * FROM {tn} WHERE date BETWEEN :d1 AND :d2 '.format(tn=self.tableReports);
      #print(queryString);
      # print("d1Timestamp: {d1}, dTimestamp: {d2}".format(d1=d1Timestamp, d2=d2Timestamp));
      c.execute(queryString, {'d1': d1Timestamp, 'd2': d2Timestamp});
        
    all_rows = c.fetchall();
    index = 0;
    templateColumns = "{index:4.4} {id:4.4} {schedule:25.25} {date:20.20} {result:20.20} {duration:9.9}";
    reportHeader = templateColumns.format(index="#", id="ID", schedule="Schedule (id)", 
                      date="Date", result="Result", duration="Duration");
                      
    print(reportHeader);
    for row in all_rows:
      index = index + 1;
      scheduleTitle = 'N/A';
      
      schedule = self.getSchedule(row['schedule']);
      if(schedule):
        scheduleTitle = schedule['title'];
      
      reportRow = templateColumns.format(index=str(index), id=str(row['id']), 
                      schedule=scheduleTitle + ' (' + str(row['schedule']) + ')', 
                      date=self.unixToDate(int(row['date'])), 
                      result=self.formatReportResult(row['Result']),
                      duration=self.secondsToTime(row['duration']));
      print(self.formatForTextDisplay(reportRow));
  
  def displayReport(self, reportId):
    c = self.conn.cursor();
    
    print("Listing details for a report");
    
    c.execute('SELECT id, Schedule, date, Result, duration, message FROM {tn} WHERE id = {ri}'.format(tn=self.tableReports, ri=reportId));
    row = c.fetchone();
    
    if(row):
      reportRow = 'ID: ' + str(row['id']) + "\n";
      reportRow += 'Schedule: ' + str(row['Schedule']) + "\n";
      reportRow += 'Date: ' + self.unixToDate(int(row['date'])) + "\n";
      reportRow += 'Result: ' + self.formatReportResult(row['Result']) + "\n";
      reportRow += 'Duration: ' + self.secondsToTime((row['duration'])) + "\n";
      if row['message'] != None:
        reportRow += 'Message:\n"' + row['message'].replace('\\n', "\n") + '"\n';
      else:
        reportRow += 'No Message\n';
      print(self.formatForTextDisplay(reportRow));
    else:
      print("ERROR: No report found with id: " + str(reportId), file=sys.stderr);
      exit(1);
    
    
  def getAllSchedules(self):
    c = self.conn.cursor();

    c.execute('SELECT * FROM {tn}'.format(tn=self.tableSchedules))
    all_rows = c.fetchall();
    return all_rows;

  def addReport(self, args):

    if(args.schedule_id == None):
      print("ERROR: no schedule ID has been specified.", file=sys.stderr);
      exit(1);

    reportMessage = None;
    if(args.stdin_message == True):
      # make sure there is no -m specified
      if(args.message != None):
        print("ERROR: --stden-message and -m cannot be used together.", file=sys.stderr);
        exit(1);

      # try to read stdin

      # are we piped to another program or connected to an interactive shell (terminal)?
      if not sys.stdin.isatty():
        #print("reading message from stdin");
        reportMessage = sys.stdin.read();
      else:
        print("ERROR: stdin is a terminal instead of piped to another program.", file=sys.stderr);
        exit(1);
    elif(args.message):
        reportMessage = args.message;

    if(args.result == None):
      print("ERROR: no result has been specified.", file=sys.stderr);
      exit(1);

    # ['done', 'done-and-verified', 'done-but-verify-error', 'failed']
    reportResult = None;
    if args.result == 'done':
      reportResult = ReportResult.DONE;
    elif args.result == 'done-and-verified':
      reportResult = ReportResult.DONE_AND_VERIFIED;
    elif args.result == 'done-but-verify-error':
      reportResult = ReportResult.DONE_BUT_VERIFICATION_ERROR;
    elif args.result == 'failed':
      reportResult = ReportResult.ERROR;
    else:
      print("ERROR: unknown result value has been specified: " + args.result, file=sys.stderr);
      exit(1);

    if(args.starting_timestamp == None):
      print("ERROR: no starting UNIX timestamp has been specified.", file=sys.stderr);
      exit(1);
    
    try:
      datetimeReport = int(args.starting_timestamp);
    except:
      print("ERROR: Could not parse timestamp '{s}'. The format is a UNIX timestamp, the number of seconds since the Unix epoch.".format(d=args.DATETIME), file=sys.stderr);
      exit(1);
    
    if(args.duration_in_seconds == None):
      reportsDuration = 0;
    else:
      try:
        reportsDuration = float(args.duration_in_seconds)
        if(reportsDuration < 0):
          print("ERROR: Duration must be zero or a positive real e.g. 0.0, 5 or 120", file=sys.stderr)
          exit(1);
      except ValueError:
        print("ERROR: Duration must be zero or a positive real e.g. 0.0, 5 or 120", file=sys.stderr)
        exit(1);

    if(self.scheduleExists(args.schedule_id) == True):
      msg = None;
      if(reportMessage != None):
        if len(reportMessage) > 100:
          msg = "<too big to list> (" + str(len(reportMessage)) + " chars total)";
        else:
          msg = "\"" + reportMessage + "\"";
      print("""Adding report with the following details: 
Schedule = {s}
Datetime = {d}
Result = {r}
Duration = {dr} seconds
Message = {msg}
""".format(s=args.schedule_id, d=datetimeReport, r=self.formatReportResult(reportResult), dr=reportsDuration, msg=msg));

      c = self.conn.cursor();
      
      try:
        
        c.execute("""
          INSERT INTO {tableName} (id, Schedule, date, Result, duration, message) 
          VALUES (NULL, :scheduleid, :date, :result, :duration, :message)
          """.format(tableName=self.tableReports),
          {
            'scheduleid': args.schedule_id,
            'date': datetimeReport,
            'result': args.result,
            'duration': reportsDuration,
            'message': reportMessage
          });

        self.conn.commit();
        print("report added");
      except sqlite3.Error as e:
        self.conn.rollback()
        print("Failed to execute SQL statement for inserting a new report: ");
        pprint(e);

      self.conn.close()
    else:
      print('ERROR: Schedule with ID {s} does not exist'.format(s=args.schedule_id));



  def deleteReport(self, args):
    c = self.conn.cursor();

    c.execute('SELECT r.id, s.id, s.title FROM {tn} r inner join {st} s on s.id = r.schedule WHERE r.id = {ri}'.format(tn=self.tableReports, st=self.tableSchedules, ri=args.ID));
    reportRow = c.fetchone();

    if(reportRow):
      print("Deleting Report with the following details ID = {id}, Schedule = {title}"
                        .format(id=args.ID, title=reportRow['title']));
      
      answer = input("WARNING: The report will be deleted! Are you sure? [y/N]");
      if(answer == "y"):
        try:
          c.execute("DELETE FROM {tn} WHERE id = {rid}".format(tn=self.tableReports, rid=args.ID));
          self.conn.commit()
        except sqlite3.Error as e: 
          self.conn.rollback()
          print("ERROR: Failed to delete report: " + e.args[0], file=sys.stderr);
      else:
          print("ERROR: User did not select yes. Nothing has been deleted.", file=sys.stderr);
          self.conn.close();
          exit(1);

    else:
      print("ERROR: No report found with id: " + str(args.ID), file=sys.stderr);
      self.conn.close()
      exit(1);

    self.conn.close()
  
  def addSchedule(self, args):
    print("Adding Schedule with the following details Title = {title}, Interval = {title}, Source Host = {sourceHost}, " +
                        "Destination Host = {destinationHost}, Source Dir. = {sourceDir}, Destination Dir. = {destinationDir}, Type = {type}"
                        .format(title=args.TITLE, interval=args.INTERVAL, sourceHost=args.SOURCE_HOST, 
                                destinationHost=args.DESTINATION_HOST, sourceDir=args.SOURCE_DIR, 
                                destinationDir=args.DESTINATION_DIR, type=args.TYPE));

    
    c = self.conn.cursor();

    try:
      c.execute("INSERT INTO {tn} (id, Title, Interval, SourceHost, DestinationHost, SourceDir, DestinationDir, Type) VALUES (NULL, \"{title}\", \"{interval}\", \"{sourceHost}\", \"{destinationHost}\", \"{sourceDir}\", \"{destinationDir}\", {type})".\
      format(tn=self.tableSchedules, title=args.TITLE, interval=args.INTERVAL, sourceHost=args.SOURCE_HOST, destinationHost=args.DESTINATION_HOST, sourceDir=args.SOURCE_DIR, destinationDir=args.DESTINATION_DIR, type=args.TYPE));
      self.conn.commit()
    except sqlite3.Error as e: 
      self.conn.rollback()
      print("An error occurred: " + e.args[0], file=sys.stderr)

    self.conn.close()

  def deleteSchedule(self, args):
    c = self.conn.cursor();

    c.execute('SELECT * FROM {tn} WHERE id = {si}'.format(tn=self.tableSchedules, si=args.ID));
    scheduleRow = c.fetchone();

    if(scheduleRow):
      reportRow = 'ID: ' + str(scheduleRow['id']) + "\n";
      reportRow += 'Schedule: ' + str(scheduleRow['Title']) + "\n";

      print("Deleting Schedule with the following details ID = {id}, Title = {title}"
                        .format(id=args.ID, title=scheduleRow['title']));

      c.execute('SELECT count(*) FROM {tn} WHERE Schedule = {si}'.format(tn=self.tableReports, si=args.ID));
      row = c.fetchone();
      numberOfReports = int(row[0]);
      deleteReports = False;

      if(numberOfReports > 0):
        answer = input("WARNING: Schedule has " + str(numberOfReports) + " reports and they will be deleted! Are you sure? [y/N]");
        if(answer == "y"):
          deleteReports = True;
        else:
            print("ERROR: User did not select yes. Nothing has been deleted.", file=sys.stderr);
            self.conn.close();
            exit(1);

      try:
        
        if(deleteReports == True):
          c.execute("DELETE FROM {tn} WHERE Schedule = {scheduleid}".format(tn=self.tableReports, scheduleid=args.ID));
        
        c.execute("DELETE FROM {tn} WHERE id = {id}".format(tn=self.tableSchedules, id=args.ID));
        self.conn.commit()
      except sqlite3.Error as e: 
        self.conn.rollback()
        print("ERROR: Failed to delete schedule: " + e.args[0], file=sys.stderr)
        exit(1);

    else:
      print("ERROR: No schedule found with id: " + str(args.ID), file=sys.stderr);
      exit(1);

    self.conn.close()

  def formatReportResult(self, reportResult):
    formmatedResult = '';
    if(reportResult == ReportResult.DONE):
      formmatedResult = 'OK (unverified)';
    elif(reportResult == ReportResult.DONE_AND_VERIFIED):
      formmatedResult = 'OK AND VERIFIED';
    elif(reportResult == ReportResult.DONE_BUT_VERIFICATION_ERROR):
      formmatedResult = 'VERIFICATION ERROR';
    elif(reportResult == ReportResult.ERROR):
      formmatedResult = 'ERROR';
    
    return formmatedResult;
  
  def unixToDate(self, reportTimestamp):
    return datetime.datetime.fromtimestamp(reportTimestamp).strftime('%Y-%m-%d %H:%M:%S');
  
  def secondsToTime(self, seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d:%02d:%02d" % (h, m, s);
  
  def parseDate(self, stringDate):
    try:
      date = datetime.datetime.strptime(stringDate, "%Y-%m-%d");
    except:
      print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd (e.g. 2015-03-16)".format(d=stringDate), file=sys.stderr);
      exit(1);
    return date;
  
  # Converts datetime to UTC timestamp (UTC is important)
  def totimestamp(self, dt):
    timestamp = time.mktime(dt.timetuple()); # DO NOT USE IT WITH UTC DATE
    return timestamp; 

  def scheduleExists(self, scheduleId):
    c = self.conn.cursor();

    queryString = 'SELECT id FROM {tn} WHERE id = {si}'.format(tn=self.tableSchedules, si=scheduleId);
    c.execute(queryString);
    if c.fetchone() != None:
      return True;
    else:
      return False;
      
  def getSchedule(self, scheduleId):
    c = self.conn.cursor();

    queryString = 'SELECT * FROM {tn} WHERE id = {si}'.format(tn=self.tableSchedules, si=scheduleId);
    c.execute(queryString);
    #print("queryString={qs}, scheduleid={si}, rowcount={rc}".format(qs=queryString, si=scheduleId, rc=c.rowcount));
    resultRow = c.fetchone();
    if resultRow != None:
      #print("true");
      return resultRow;
    else:
      #print("false");
      return False;
  
  def checkReports(self, args):
    doEmailReport = False;
    
    if(args.email):
      doEmailReport = True;
      
    if(args.date):
      try:
        dateForChecking = datetime.datetime.strptime(args.date, "%Y-%m-%d");
      except:
        print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd (e.g. 2015-03-16)".format(d=args.date), file=sys.stderr);
        exit(1);
      self.checkReportsByDate(dateForChecking, doEmailReport);
    else:
      if(args.days):
        try:
          numberOfdaysBeforeCheckDate = int(args.days)
        except ValueError:
          print("ERROR: Number of Days must be a positive integer e.g. 5 or 120", file=sys.stderr)
          exit(1);
          
        if(numberOfdaysBeforeCheckDate < 1 or numberOfdaysBeforeCheckDate > 40000):
          print("ERROR: Number of Days must be a positive integer e.g. 5 or 120", file=sys.stderr)
          exit(1);
          
        dateForChecking = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0);
        dateForChecking = dateForChecking - datetime.timedelta(days=numberOfdaysBeforeCheckDate);
        
      else:
        # dafault: check yesterday's date. 
        dateForChecking = datetime.datetime.now();
        
      # get current date and substract 1
      dateForChecking = dateForChecking - datetime.timedelta(days=1);
      self.checkReportsByDate(dateForChecking, doEmailReport);
  
  def notify(self, message, notifyType, dateForChecking):
    headers = [];
    if(notifyType == self.NOTIFY_OK):
      subject = 'NekBackupMonitor Report ' + dateForChecking.strftime("%Y-%m-%d");
    elif(notifyType == self.NOTIFY_ERROR):
      subject = 'ERROR!!! NekBackupMonitor Report ' + dateForChecking.strftime("%Y-%m-%d");
    
    print("Sending email...");
    self.sendEmail(message, subject, headers);
    
  def sendEmail(self, message, subject, headers):
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject;
    msg['From'] = self.fromEmail;
    msg['To'] = self.toEmail;

    # add headers if any
    if len(headers) > 0:
      for h in headers:
        msg[h[0]] = h[1];

    # Create the body of the message (a plain-text and an HTML version).
    text = message;
    html = """\
    <html>
      <head></head>
      <body>
        <pre>"""
    html += message;
    html += """</pre>
      </body>
    </html>
    """
    
    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    msg.attach(part2)


    # Send the message via our own SMTP server, but don't include the
    # envelope header.
    p = Popen(["sendmail", "-t", "-oi"], stdin=PIPE, universal_newlines=True)
    p.communicate(msg.as_string())
  
  def checkReportsByDate(self, dateForChecking, doEmailReport):
    reportText = '';
    reportTableText = '';
    
    schedulesDone = []
    allSchedules = self.getAllSchedules();
    
    reportTableText += "Backup report for date {d}\n\n".format(d=dateForChecking.strftime("%Y-%m-%d"));
    d1 = dateForChecking.replace(hour=0, minute=0, second=0, microsecond=0);
    d2 = d1 + datetime.timedelta(days=1);
    d1Timestamp = self.totimestamp(d1);
    d2Timestamp = self.totimestamp(d2);
    #print("d1 = {d1}, d2 = {d2}".format(d1=d1, d2=d2));
    #exit(0);
    
    c = self.conn.cursor();

    # 1) Contents of all columns for row that match a certain value in 1 column
    queryString = 'SELECT * FROM {tn} WHERE date BETWEEN {d1} AND {d2}'.format(tn=self.tableReports, d1=d1Timestamp, d2=d2Timestamp);
    #print(queryString);
    c.execute(queryString);
    all_rows = c.fetchall();
    for row in all_rows:
      rowSchedule = self.getSchedule(row['Schedule']);
      #print(rowSchedule);
      if(rowSchedule != None):
        schedulesDone.append(row);    
    allOK = True;
    
    templateColumns = "{id:4.4} {sourcehost:10.10} {title:18.18} {scheduledfor:14.14} {result:18.18} {verified:20.20} {duration:9.9}\n";
    reportTableText += templateColumns.format(id="ID", sourcehost="Host", title="Title",
                      scheduledfor="ScheduledFor", 
                      result="Result", verified="Verified",
                      duration="Duration");
    #reportTableText += "ID    Title              Result                Verified" + "\n";
    for schedule in allSchedules:
      isTried = False;
      isDone = False;
      isVerified = False;
      hadError = False;
      hasVerificationErrors = False;
      scheduleDuration = 0;
      
      base = d1;
      itr = croniter(schedule['interval'], base);
      scheduleNextIeration = itr.get_next();
      reportTableText += "{id:4.4} {sourcehost:10.10} {title:18.18} {scheduledfor:14.14} ".format(id=str(schedule['id']), 
                                        sourcehost=schedule['sourcehost'],
                                        title=str(schedule['title']),
                                        scheduledfor=datetime.datetime.fromtimestamp(scheduleNextIeration).strftime('%H:%M:%S'));
      
      resultText = '';
      verifiedText = '';
      # check if it is scheduled for the date of checking
      if(scheduleNextIeration >= d1Timestamp and scheduleNextIeration <= d2Timestamp):
        #print("Scheduled date is between the checking date");
        for scheduleDone in schedulesDone:
          if(schedule['id'] == scheduleDone['Schedule']):
            isTried = True;
            scheduleDuration = scheduleDone['duration'];
            #print("result = {s}".format(s=scheduleDone['result']));
            if(scheduleDone['result'] == 1):
              isDone = True;
            if(scheduleDone['result'] == 2):
              isDone = True;
              isVerified = True;
            if(scheduleDone['result'] == 3):
              isDone = True;
              isVerified = False;
              hasVerificationErrors = True;
            elif(scheduleDone['result'] == 0):
              hadError = True;
        
        #print("isTried = {t}, isDone = {d}, hadError = {e}".format(t=isTried,d=isDone,e=hadError));
        
        if(isTried == True):
          if(isDone == True and hadError == True):
            resultText += "OK (with retries)";
            reportText += "Schedule {n} with id {i} is done But had error tries".format(n=schedule['title'], i=schedule['id']) + "\n";
          elif(isDone == True and hadError == False):
            resultText += "OK";
            reportText += "Schedule {n} with id {i} is done".format(n=schedule['title'], i=schedule['id']) + "\n";
          elif(hadError == True):
            allOK = False;
            resultText += "ERROR";
            reportText += "Schedule {n} with id {i} had Error(s)".format(n=schedule['title'], i=schedule['id']) + "\n";
          else:
            allOK = False;
            resultText += "Tried with ERROR";
            reportText += "Schedule {n} with id {i} had been Tried but not done and no Error(s)".format(n=schedule['title'], i=schedule['id']) + "\n";
          
          if(isVerified == True):
            verifiedText += "VERIFIED";
            reportText += "Schedule {n} with id {i} is verified".format(n=schedule['title'], i=schedule['id']) + "\n";
          else:
            if(hasVerificationErrors == True):
              verifiedText += "VERIFICATION ERROR";
              reportText += "Schedule {n} with id {i} has verification errors.".format(n=schedule['title'], i=schedule['id']) + "\n";
            else:
              verifiedText += "NO";
              reportText += "Schedule {n} with id {i} is not verified".format(n=schedule['title'], i=schedule['id']) + "\n";
        else:
          allOK = False;
          resultText += "Missing";
          verifiedText += "NO";
          reportText += "Schedule {n} with id {i} wasn't tried at all".format(n=schedule['title'], i=schedule['id']) + "\n";
      else:
        resultText += "Not scheduled";
        verifiedText += "N/A";
        #reportText += "Schedule {n} with id {i} wasn't tried at all".format(n=schedule['title'], i=schedule['id']) + "\n";
        reportText += "Schedule {n} was not scheduled for the date".format(n=schedule['title']);
      
      reportTableText += "{result:18.18} {verified:20.20} {duration:9.9}\n".format(result=resultText, verified=verifiedText, duration=self.secondsToTime(scheduleDuration));
    if(allOK == True):
      notifyType = self.NOTIFY_OK;
    elif(allOK == False):
      notifyType = self.NOTIFY_ERROR;
    reportTableText += "\n\nReport created on {s}".format(s=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"));
    
    print(self.formatForTextDisplay(reportTableText));
    
    
    #print(reportText);
    if(doEmailReport == True):
      self.notify(self.formatForHTMLDisplay(reportTableText), notifyType, dateForChecking);
    
  def formatForTextDisplay(self, stringText):
    stringTextFormatted = stringText.replace('OK', bcolors.OKGREEN + "OK" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('OK AND VERIFIED', bcolors.OKGREEN + "OK AND VERIFIED" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('(with retries)', bcolors.WARNING + "(with retries)" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('(unverified)', bcolors.WARNING + "(unverified)" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('NO', bcolors.WARNING + "NO" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('VERIFICATION ERROR', bcolors.FAIL + "VERIFICATION ERROR" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('ERROR', bcolors.FAIL + "ERROR" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('Missing', bcolors.FAIL + "Missing" + bcolors.ENDC);
    stringTextFormatted = stringTextFormatted.replace('VERIFIED', bcolors.OKGREEN + "VERIFIED" + bcolors.ENDC);
    return stringTextFormatted;
  
  def formatForHTMLDisplay(self, stringText):
    stringHTMLFormatted = stringText.replace('OK', "<span style='color: green;'>" + "OK" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('OK AND VERIFIED', "<span style='color: green;'>" + "OK AND VERIFIED" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('(with retries)', "<span style='color: darkorange;'>" + "(with retries)" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('(unverified)', "<span style='color: darkorange;'>" + "(unverified)" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('NO', "<span style='color: darkorange;'>" + "NO" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('VERIFICATION ERROR', "<span style='color: red;'>" + "VERIFICATION ERROR" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('ERROR', "<span style='color: red;'>" + "ERROR" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('Missing', "<span style='color: red;'>" + "Missing" + "</span>");
    stringHTMLFormatted = stringHTMLFormatted.replace('VERIFIED', "<span style='color: green;'>" + "VERIFIED" + "</span>");
    
    return stringHTMLFormatted;

class bcolors:
  HEADER = '\033[95m'
  OKBLUE = '\033[94m'
  OKGREEN = '\033[92m'
  WARNING = '\033[93m'
  FAIL = '\033[91m'
  ENDC = '\033[0m'
  BOLD = '\033[1m'
  UNDERLINE = '\033[4m'

class ReportResult(Enum):
  ERROR = 0
  DONE = 1
  DONE_AND_VERIFIED = 2
  DONE_BUT_VERIFICATION_ERROR = 3
  
if __name__ == '__main__':
  NekBackupMonitor()
