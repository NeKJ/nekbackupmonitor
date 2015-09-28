#!/usr/bin/python2

import argparse
import sys
import sqlite3
import datetime
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from subprocess import Popen, PIPE
from croniter import croniter

class NekBackupMonitor(object):
	
	sqlite_file = './NekBackupMonitor.db';
	tableSchedules = 'schedules';
	tableReports = 'reports';
	fromEmail = 'email@example.com';
	toEmail = 'email@example.com';

	NOTIFY_OK = 1;
	NOTIFY_ERROR = 2;

	# Connecting to the database file
	conn = sqlite3.connect(sqlite_file); # @UndefinedVariable
	conn.row_factory = sqlite3.Row; # @UndefinedVariable
	
	def __init__(self):

		parser = argparse.ArgumentParser(prog='nekbackupmonitor.py');

		p_report = argparse.ArgumentParser(add_help=False);
		p_report.add_argument('SCHEDULE_ID', type=int, help='report schedule id');
		p_report.add_argument('DATETIME', type=str, help='report time');
		p_report.add_argument('RESULT', type=int, help='report time');
		p_report.add_argument('-m', '--message', help='report time');
		
		p_check = argparse.ArgumentParser(add_help=False);
		p_check.add_argument('-d', '--date', type=str, help='Date. The format is YYYY-mm-dd (e.g. 2015-03-16)');
		p_check.add_argument('-m', '--email', action="store_true", help='Also email the report.');
		
		p_schedules = argparse.ArgumentParser(add_help=False);
		p_schedules.add_argument('-f', '--full', action="store_true", help='List with full details.');
		
		p_reports = argparse.ArgumentParser(add_help=False);
		p_reports.add_argument('-s', '--schedule', type=int, help='ID of schedule. List reports specifically for a schedule.');
		p_reports.add_argument('-r', '--report', type=int, help='ID of report. List details about a specific report.');

		sp = parser.add_subparsers();
		sp_list_schedules = sp.add_parser('list-schedules', parents=[p_schedules], help='Lists schedules');
		sp_list_schedules.set_defaults(which='list-schedules');
		
		sp_list_reports = sp.add_parser('list-reports', parents=[p_reports], help='Lists reports');
		sp_list_reports.set_defaults(which='list-reports');
		
		sp_check = sp.add_parser('check', parents=[p_check], help='Check reports');
		sp_check.set_defaults(which='check');
		
		sp_add = sp.add_parser('add', parents=[p_report], help='Add backup report');
		sp_add.set_defaults(which='add');
		
		args = parser.parse_args();
		if(args.which == 'list-schedules'):
			self.listSchedules(args);
		elif(args.which == 'list-reports'):
			self.listReports(args);
		elif(args.which == 'add'):
			self.addReport(args);
		elif(args.which == 'check'):
			self.checkReports(args);
		

	def listSchedules(self, args):
		print("Listing Schedules");
		
		all_rows = self.getAllSchedules();
		
		if(args.full):
			print("#	ID		Title			Interval		SourceHost		DestHost		SourceDir		DestDir		Type");
			index = 0;
			for row in all_rows:
				index = index + 1;
				reportRow = str(index);
				reportRow += '  ' + str(row['id']);
				reportRow += '  ' + str(row['title']);
				reportRow += '		' + str(row['interval']);
				reportRow += '		' + str(row['sourcehost']);
				reportRow += '		' + str(row['destinationhost']);
				reportRow += '		' + str(row['sourcedir']);
				reportRow += '		' + str(row['destinationdir']);
				reportRow += '		' + str(row['type']);
				print(reportRow);
		else:
			print("#	ID	Title			Interval		SourceHost		DestHost");
			index = 0;
			for row in all_rows:
				index = index + 1;
				reportRow = str(index);
				reportRow += '	' + str(row['id']);
				reportRow += '	' + str(row['title']);
				reportRow += '		' + str(row['interval']);
				reportRow += '		' + str(row['sourcehost']);
				reportRow += '		' + str(row['destinationhost']);
				print(reportRow);
			
		
	def listReports(self, args):
		c = self.conn.cursor();
		
		if(args.report):
			self.displayReport(args.report);
			return;
		
		if(args.schedule):
			selectedSchedule = self.getSchedule(args.schedule);
			if(selectedSchedule):
				print("Listing Reports for schedule " + selectedSchedule['title'] + " (ID: " + str(selectedSchedule['id']) + ")");
				c.execute('SELECT id, Schedule, date, Result, message FROM {tn} WHERE schedule = {si}'.format(tn=self.tableReports, si=args.schedule));
			else:
				print("ERROR: No schedule found with id: " + str(args.schedule));
				exit(1);
		else:
			print("Listing Reports");
			c.execute('SELECT * FROM {tn}'.format(tn=self.tableReports));
		
		all_rows = c.fetchall();
		index = 0;
		print("#		ID		Schedule		Date			Result");
		for row in all_rows:
			index = index + 1;
			reportRow = str(index);
			reportRow += '		' + str(row['id']);
			reportRow += '		' + str(row['Schedule']);
			reportRow += '			' + self.unixToDate(row['date']);
			reportRow += '	' + self.formatReportResult(row['Result']);
			#reportRow += 'message: ' + row['message'];
			print(reportRow);
	
	def displayReport(self, reportId):
		c = self.conn.cursor();
		
		print("Listing details for a report");
		
		c.execute('SELECT id, Schedule, date, Result, message FROM {tn} WHERE id = {ri}'.format(tn=self.tableReports, ri=reportId));
		row = c.fetchone();
		
		if(row):
			reportRow = 'ID: ' + str(row['id']) + "\n";
			reportRow += 'Schedule: ' + str(row['Schedule']) + "\n";
			reportRow += 'Date: ' + self.unixToDate(row['date']) + "\n";
			reportRow += 'Result: ' + self.formatReportResult(row['Result']) + "\n";
			reportRow += 'Message:\n' + row['message'].replace('\\n', "\n") + "\n";
			print(reportRow);
		else:
			print("ERROR: No report found with id: " + str(reportId));
			exit(1);
		
		
	def getAllSchedules(self):
		c = self.conn.cursor();

		c.execute('SELECT * FROM {tn}'.format(tn=self.tableSchedules))
		all_rows = c.fetchall();
		return all_rows;

	def addReport(self, args):
		print("Adding report with the following details Schedule = {s}, Datetime = {d}, Result = {r}".format(s=args.SCHEDULE_ID, d=args.DATETIME, r=args.RESULT));
		
		if(args.DATETIME):
			try:
				datetimeReport = datetime.datetime.strptime(args.DATETIME, "%Y-%m-%d %H:%M:%S");
			except:
				print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd HH:MM:SS (e.g. 2015-03-16 12:51:23)".format(d=args.DATETIME));
				exit(1);
			
		if(self.scheduleExists(args.SCHEDULE_ID) == True):
			c = self.conn.cursor();

			Reporttimestamp = self.totimestamp(datetimeReport);
			
			try:
				c.execute("INSERT INTO {tn} (id, Schedule, date, Result, message) VALUES (NULL, {scheduleid}, {date}, {result}, \"{message}\")".\
				format(tn=self.tableReports, scheduleid=args.SCHEDULE_ID, date=Reporttimestamp, result=args.RESULT, message=args.message))
			except sqlite3.Error as e: # @UndefinedVariable
				print("An error occurred: " + e.args[0]) # @UndefinedVariable
				
			self.conn.commit() # @UndefinedVariable
			self.conn.close() # @UndefinedVariable
		else:
			print('ERROR: Schedule {} does not exist'.format(args.SCHEDULE_ID));
	
	def formatReportResult(self, reportResult):
		formmatedResult = '';
		if(reportResult == 1):
			formmatedResult = 'DONE';
		elif(reportResult == 0):
			formmatedResult = 'ERROR';
		
		return formmatedResult;
	
	def unixToDate(self, reportTimestamp):
		return datetime.datetime.fromtimestamp(reportTimestamp).strftime('%Y-%m-%d %H:%M:%S');
	
	# Converts datetime to UTC timestamp (UTC is important)
	def totimestamp(self, dt):
		timestamp = time.mktime(dt.timetuple()); # DO NOT USE IT WITH UTC DATE
		return timestamp; 
   
	def scheduleExists(self, scheduleId):
		c = self.conn.cursor();

		queryString = 'SELECT id FROM {tn} WHERE id = {si}'.format(tn=self.tableSchedules, si=scheduleId);
		c.execute(queryString);
		#print("queryString={qs}, scheduleid={si}, rowcount={rc}".format(qs=queryString, si=scheduleId, rc=c.rowcount));
		if c.fetchone() != None:
			#print("true");
			return True;
		else:
			#print("false");
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
				print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd (e.g. 2015-03-16)".format(d=args.date));
				exit(0);
			self.checkReportsByDate(dateForChecking, doEmailReport);
		else:
			# dafault: check yesterday's date. 
			dateForChecking = datetime.datetime.now();
			# get current date and substract 1
			dateForChecking = dateForChecking - datetime.timedelta(days=1);
			self.checkReportsByDate(dateForChecking, doEmailReport);
	
	def notify(self, message, notifyType):
		todayText = datetime.datetime.now();
		
		if(notifyType == self.NOTIFY_OK):
			subject = 'NekBackupMonitor Report';
		elif(notifyType == self.NOTIFY_ERROR):
			subject = 'ERROR!!! NekBackupMonitor Report';
		
		print("Sending email...");
		self.sendEmail(message, subject);
		
	def sendEmail(self, message, subject):
		
		msg = MIMEMultipart('alternative')
		msg['Subject'] = subject;
		msg['From'] = self.fromEmail;
		msg['To'] = self.toEmail;


		# Create the body of the message (a plain-text and an HTML version).
		text = "This is a test message.\nText and html."
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
		p = Popen(["/usr/sbin/sendmail", "-t", "-oi"], stdin=PIPE, universal_newlines=True)
		p.communicate(msg.as_string())
	
	def checkReportsByDate(self, dateForChecking, doEmailReport):
		reportText = '';
		reportTableText = '';
		
		schedulesDone = []
		allSchedules = self.getAllSchedules();
		
		reportTableText += "Checking Reports for date {d}\n\n".format(d=dateForChecking.strftime("%Y-%m-%d"));
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
			rowDate = self.unixToDate(row['date']);
			rowSchedule = self.getSchedule(row['Schedule']);
			#print(rowSchedule);
			if(rowSchedule != None):
				schedulesDone.append(row);
				#print("schedule = {s}, date = {d}, result = {r}".format(s=rowSchedule['id'], d=rowDate, r=row['result']));
			

		
		index = 0;
		allOK = True;
		
		reportTableText += "ID    Title              Result              " + "\n";
		for schedule in allSchedules:
			isTried = False;
			isDone = False;
			hadError = False;
			
			base = d1;
			itr = croniter(schedule['interval'], base)
			#itr = croniter("* * 1,12,31,27 * *", base)
			#itr = croniter("0 12 * * *", base)
			scheduleNextIeration = itr.get_next();
			#print("Schedule {n} with id {i} and interval {int} next backup date scheduled = {ni}".format(n=schedule['title'], i=schedule['id'],int=schedule['interval'], ni=self.unixToDate(scheduleNextIeration)) + "\n");
			
			#reportRow = str(index);
			reportTableText += "{id:5.5} {title:18.18} ".format(id=str(schedule['id']), title=str(schedule['title']));
			
			# check if it is scheduled for the date of checking
			if(scheduleNextIeration >= d1Timestamp and scheduleNextIeration <= d2Timestamp):
				#print("Scheduled date is between the checking date");
				for scheduleDone in schedulesDone:
					if(schedule['id'] == scheduleDone['Schedule']):
						isTried = True;
						#print("result = {s}".format(s=scheduleDone['result']));
						if(scheduleDone['result'] == 1):
							isDone = True;
						elif(scheduleDone['result'] == 0):
							hadError = True;
				
				#print("isTried = {t}, isDone = {d}, hadError = {e}".format(t=isTried,d=isDone,e=hadError));
				
				if(isTried == True):
					if(isDone == True and hadError == True):
						reportTableText += "OK (with retries)" + "\n";
						reportText += "Schedule {n} with id {i} is done But had error tries".format(n=schedule['title'], i=schedule['id']) + "\n";
					elif(isDone == True and hadError == False):
						reportTableText += "OK" + "\n";
						reportText += "Schedule {n} with id {i} is done".format(n=schedule['title'], i=schedule['id']) + "\n";
					elif(hadError == True):
						allOK = False;
						reportTableText += "ERROR" + "\n";
						reportText += "Schedule {n} with id {i} had Error(s)".format(n=schedule['title'], i=schedule['id']) + "\n";
					else:
						allOK = False;
						reportTableText += "Tried with ERROR" + "\n";
						reportText += "Schedule {n} with id {i} had been Tried but not done and no Error(s)".format(n=schedule['title'], i=schedule['id']) + "\n";
				else:
					allOK = False;
					reportTableText += "NO TRIES AT ALL" + "\n";
					reportText += "Schedule {n} with id {i} wasn't tried at all".format(n=schedule['title'], i=schedule['id']) + "\n";
			else:
				reportTableText += "Not scheduled" + "\n";
				#reportText += "Schedule {n} with id {i} wasn't tried at all".format(n=schedule['title'], i=schedule['id']) + "\n";
				reportText += "Schedule {n} was not scheduled for the date".format(n=schedule['title']);
			
		if(allOK == True):
			notifyType = self.NOTIFY_OK;
		elif(allOK == False):
			notifyType = self.NOTIFY_ERROR;
		reportTableText += "\n\nReport created on {s}".format(s=datetime.datetime.now());
		print(reportTableText);
		#print(reportText);
		if(doEmailReport == True):
			self.notify(reportTableText, notifyType);
		

if __name__ == '__main__':
	NekBackupMonitor()
