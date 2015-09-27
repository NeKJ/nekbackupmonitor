#!/usr/bin/python

import argparse
import sys
import sqlite3
import datetime
from email.mime.text import MIMEText
from subprocess import Popen, PIPE
from croniter import croniter

class NekBackupMonitor(object):
	
	sqlite_file = 'NekBackupMonitor.db';
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
		
		p_check = argparse.ArgumentParser(add_help=False);
		p_check.add_argument('DATE', type=str, help='Date. The format is YYYY-mm-dd (e.g. 2015-03-16)');

		sp = parser.add_subparsers();
		sp_list_schedules = sp.add_parser('list-schedules', help='Lists schedules');
		sp_list_schedules.set_defaults(which='list-schedules');
		
		sp_list_reports = sp.add_parser('list-reports', help='Lists reports');
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
		for row in all_rows:
			print('|'.join(str(m) for m in row));
			
		
	def listReports(self, args):
		c = self.conn.cursor();
		
		print("Listing Reports");
		
		c.execute('SELECT * FROM {tn}'.\
		format(tn=self.tableReports));
		all_rows = c.fetchall();
		for row in all_rows:
			print('|'.join(str(m) for m in row));
		
	def getAllSchedules(self):
		c = self.conn.cursor();

		c.execute('SELECT * FROM {tn}'.format(tn=self.tableSchedules))
		all_rows = c.fetchall();
		return all_rows;

	def addReport(self, args):
		print("Adding report with the following details Schedule = {s}, Datetime = {d}, Result = {r}".format(s=args.SCHEDULE_ID, d=args.DATETIME, r=args.RESULT));
		
		if(self.scheduleExists(args.SCHEDULE_ID) == True):
			c = self.conn.cursor();

			# A) Inserts an ID with a specific value in a second column 
			try:
				c.execute("INSERT INTO {tn} (id, Schedule, date, Result) VALUES (NULL, {scheduleid}, {date}, {result})".\
				format(tn=self.tableReports, scheduleid=args.SCHEDULE_ID, date=args.DATETIME, result=args.RESULT))
			except sqlite3.IntegrityError: # @UndefinedVariable
				print('ERROR: ID already exists in PRIMARY KEY column')
				
			conn.commit() # @UndefinedVariable
			conn.close() # @UndefinedVariable
		else:
			print('ERROR: Schedule {} does not exist'.format(args.SCHEDULE_ID));
			

		'''
		# B) Tries to insert an ID (if it does not exist yet)
		# with a specific value in a second column 
		c.execute("INSERT OR IGNORE INTO {tn} ({idf}, {cn}) VALUES (123456, 'test')".\
			format(tn=table_name, idf=id_column, cn=column_name))

		# C) Updates the newly inserted or pre-existing entry            
		c.execute("UPDATE {tn} SET {cn}=('Hi World') WHERE {idf}=(123456)".\
			format(tn=table_name, cn=column_name, idf=id_column))
		'''
		
		
	
	def unixToDate(self, reportTimestamp):
		return datetime.datetime.fromtimestamp(reportTimestamp).strftime('%Y-%m-%d %H:%M:%S');
	
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
		if(args.DATE):
			try:
				dateForChecking = datetime.datetime.strptime(args.DATE, "%Y-%m-%d");
			except:
				print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd (e.g. 2015-03-16)".format(d=args.DATE));
			self.checkReportsByDate(dateForChecking);
	
	def notify(self, message, notifyType):
		todayText = datetime.datetime.now();
		
		if(notifyType == self.NOTIFY_OK):
			subject = 'NekBackupMonitor Report for {s}'.format(s=todayText.strftime('%Y/%m/%d %H:%M:%S'));
		elif(notifyType == self.NOTIFY_ERROR):
			subject = 'ERROR!!! NekBackupMonitor Report for {s}'.format(s=todayText.strftime('%Y/%m/%d %H:%M:%S'));
		
		self.sendEmail(message, subject);
		
	def sendEmail(self, message, subject):
		
		msg = MIMEText(message)
		msg['Subject'] = subject;
		msg['From'] = self.fromEmail;
		msg['To'] = self.toEmail;

		# Send the message via our own SMTP server, but don't include the
		# envelope header.
		p = Popen(["/usr/bin/sendmail", "-t", "-oi"], stdin=PIPE, universal_newlines=True)
		p.communicate(msg.as_string())
	
	def checkReportsByDate(self, dateForChecking):
		schedulesDone = []
		allSchedules = self.getAllSchedules();
		
		print("Checking Reports for date {d}".format(d=dateForChecking));
		d1 = dateForChecking.replace(hour=0, minute=0, second=0, microsecond=0);
		d2 = d1 + datetime.timedelta(days=1);
		d1Timestamp = d1.timestamp();
		d2Timestamp = d2.timestamp();
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
				print("schedule = {s}, date = {d}, result = {r}".format(s=rowSchedule['id'], d=rowDate, r=row['result']));
			

		reportText = '';
		allOK = True;
		
		for schedule in allSchedules:
			isTried = False;
			isDone = False;
			hadError = False;
			
			base = d1;
			#itr = croniter(schedule['interval'], base)
			#itr = croniter("* * 1,12,31,27 * *", base)
			#itr = croniter("0 12 * * *", base)
			scheduleNextIeration = itr.get_next();
			print("Schedule {n} with id {i} and interval {int} next backup date scheduled = {ni}".format(n=schedule['title'], i=schedule['id'],int=schedule['interval'], ni=self.unixToDate(scheduleNextIeration)) + "\n");
			
			# check if it is scheduled for the date of checking
			if(scheduleNextIeration >= d1Timestamp and scheduleNextIeration <= d2Timestamp):
				print("Scheduled date is between the checking date");
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
						reportText += "Schedule {n} with id {i} is done But had error tries".format(n=schedule['title'], i=schedule['id']) + "\n";
					elif(isDone == True and hadError == False):
						reportText += "Schedule {n} with id {i} is done".format(n=schedule['title'], i=schedule['id']) + "\n";
					elif(hadError == True):
						allOK = False;
						reportText += "Schedule {n} with id {i} had Error(s)".format(n=schedule['title'], i=schedule['id']) + "\n";
					else:
						allOK = False;
						reportText += "Schedule {n} with id {i} had been Tried but not done and no Error(s)".format(n=schedule['title'], i=schedule['id']) + "\n";
				else:
					allOK = False;
					reportText += "Schedule {n} with id {i} wasn't tried at all".format(n=schedule['title'], i=schedule['id']) + "\n";
			else:
				print("Scheduled date {nsd}is NOT between the checking date {cd}".format(nsd=self.unixToDate(scheduleNextIeration), cd=dateForChecking));
			
		if(allOK == True):
			notifyType = self.NOTIFY_OK;
		elif(allOK == False):
			notifyType = self.NOTIFY_ERROR;
		
		print(reportText);
		self.notify(reportText, notifyType);

if __name__ == '__main__':
	NekBackupMonitor()
