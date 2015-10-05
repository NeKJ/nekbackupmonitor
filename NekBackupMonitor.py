#!/usr/bin/python2

import argparse;
import sqlite3;
import datetime;
import time;
from email.mime.text import MIMEText;
from email.mime.multipart import MIMEMultipart;
from subprocess import Popen, PIPE;
from croniter import croniter;

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
		p_report.add_argument('DATETIME', type=str, help='report date and time');
		p_report.add_argument('RESULT', type=int, help='report resul');
		p_report.add_argument('DURATION', type=float, help='report duration');
		p_report.add_argument('-m', '--message', help='report message');
		
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
				c.execute('SELECT id, Schedule, date, Result, duration, message FROM {tn} WHERE schedule = {si}'.format(tn=self.tableReports, si=args.schedule));
			else:
				print("ERROR: No schedule found with id: " + str(args.schedule));
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
						print("Number of Days must be an positve integer e.g. 5 or 120")
						exit(1);
					if(numberOfdaysListReports > 0 and numberOfdaysListReports < 40000):
						listReportsFromDate = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0);
						listReportsFromDate = listReportsFromDate - datetime.timedelta(days=numberOfdaysListReports);
						listReportsToDate = datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999);
					else:
						print("Number of Days must be an positve integer e.g. 5 or 120")
						exit(1);
				else:
					listReportsFromDate = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0);
					listReportsFromDate = listReportsFromDate - datetime.timedelta(days=7);
					listReportsToDate = datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999);
				
			if(listReportsToDate < listReportsFromDate):
				print("To Date must be after the From Date.");
				exit(1);
			d1 = listReportsFromDate;
			d2 = listReportsToDate;
			#d2 = d1 + datetime.timedelta(days=1);
			d1Timestamp = self.totimestamp(d1);
			d2Timestamp = self.totimestamp(d2);
			print("Listing Reports from date {d1} to {d2}".format(d1=listReportsFromDate.strftime("%Y-%m-%d %H:%M:%S"), d2=listReportsToDate.strftime("%Y-%m-%d %H:%M:%S")));
			queryString = 'SELECT * FROM {tn} WHERE date BETWEEN {d1} AND {d2} '.format(tn=self.tableReports, d1=d1Timestamp, d2=d2Timestamp)
			#print(queryString);
			c.execute(queryString);
				
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
											date=self.unixToDate(row['date']), 
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
			reportRow += 'Date: ' + self.unixToDate(row['date']) + "\n";
			reportRow += 'Result: ' + self.formatReportResult(row['Result']) + "\n";
			reportRow += 'Duration: ' + self.secondsToTime((row['duration'])) + "\n";
			reportRow += 'Message:\n' + row['message'].replace('\\n', "\n") + "\n";
			print(self.formatForTextDisplay(reportRow));
		else:
			print("ERROR: No report found with id: " + str(reportId));
			exit(1);
		
		
	def getAllSchedules(self):
		c = self.conn.cursor();

		c.execute('SELECT * FROM {tn}'.format(tn=self.tableSchedules))
		all_rows = c.fetchall();
		return all_rows;

	def addReport(self, args):
		print("Adding report with the following details Schedule = {s}, Datetime = {d}, Result = {r}, Duration = {dr}".format(s=args.SCHEDULE_ID, d=args.DATETIME, r=args.RESULT, dr=args.DURATION));
		
		if(args.DATETIME):
			try:
				datetimeReport = datetime.datetime.strptime(args.DATETIME, "%Y-%m-%d %H:%M:%S");
			except:
				print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd HH:MM:SS (e.g. 2015-03-16 12:51:23)".format(d=args.DATETIME));
				exit(1);
		
		if(args.DURATION >= 0):
				try:
					reportsDuration = float(args.DURATION)
					if(reportsDuration < 0):
						print("Duration must be zero or a positive real e.g. 0.0, 5 or 120")
						exit(1);
				except ValueError:
					print("Duration must be zero or a positive real e.g. 0.0, 5 or 120")
					exit(1);
		
		if(self.scheduleExists(args.SCHEDULE_ID) == True):
			c = self.conn.cursor();

			Reporttimestamp = self.totimestamp(datetimeReport);
			
			try:
				c.execute("INSERT INTO {tn} (id, Schedule, date, Result, duration, message) VALUES (NULL, {scheduleid}, {date}, {result}, {duration}, \"{message}\")".\
				format(tn=self.tableReports, scheduleid=args.SCHEDULE_ID, date=Reporttimestamp, result=args.RESULT, duration=reportsDuration, message=args.message));
			except sqlite3.Error as e: # @UndefinedVariable
				print("An error occurred: " + e.args[0]) # @UndefinedVariable
				
			self.conn.commit() # @UndefinedVariable
			self.conn.close() # @UndefinedVariable
		else:
			print('ERROR: Schedule {s} does not exist'.format(s=args.SCHEDULE_ID));
	
	def formatReportResult(self, reportResult):
		formmatedResult = '';
		if(reportResult == 1):
			formmatedResult = 'OK (unverified)';
		elif(reportResult == 2):
			formmatedResult = 'OK AND VERIFIED';
		elif(reportResult == 3):
			formmatedResult = 'VERIFICATION ERROR';
		elif(reportResult == 0):
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
			print("ERROR: Could not parse date '{d}'. The format is YYYY-mm-dd (e.g. 2015-03-16)".format(d=stringDate));
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
			if(args.days):
				try:
					numberOfdaysBeforeCheckDate = int(args.days)
				except ValueError:
					print("Number of Days must be a positive integer e.g. 5 or 120")
					exit(1);
					
				if(numberOfdaysBeforeCheckDate < 1 or numberOfdaysBeforeCheckDate > 40000):
					print("Number of Days must be a positive integer e.g. 5 or 120")
					exit(1);
					
				dateForChecking = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0);
				dateForChecking = dateForChecking - datetime.timedelta(days=numberOfdaysBeforeCheckDate);
				
			else:
				# dafault: check yesterday's date. 
				dateForChecking = datetime.datetime.now();
				
			# get current date and substract 1
			dateForChecking = dateForChecking - datetime.timedelta(days=1);
			self.checkReportsByDate(dateForChecking, doEmailReport);
	
	def notify(self, message, notifyType):
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
		#reportTableText += "ID    Title              Result              	Verified" + "\n";
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
				resultText += "Not scheduled" + "\n";
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
			self.notify(self.formatForHTMLDisplay(reportTableText), notifyType);
		
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
	
if __name__ == '__main__':
	NekBackupMonitor()
