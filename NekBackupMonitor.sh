#!/bin/bash

DatabaseFilename="NekBackupMonitor.db";
TableSchedulesName="schedules";
TableBackupsName="backups";


function ListSchedules() {
	# Getting data
	LIST=`sqlite3 $DatabaseFilename "SELECT * FROM $TableSchedulesName"`;

	echo "Id		Title		Interval		SourceHost		DestinationHost		SourceDir		SourceDir		DestinationDir		Type";
	echo $LIST | while read ROW; do
	   #echo "do stuff with $prkey"
	#done

	# For each row
	#for ROW in $LIST; do

		# Parsing data (sqlite3 returns a pipe separated string)
		Id=`echo $ROW | awk '{split($0,a,"|"); print a[1]}'`;
		Title=`echo $ROW | awk '{split($0,a,"|"); print a[2]}'`;
		Interval=`echo $ROW | awk '{split($0,a,"|"); print a[3]}'`;
		SourceHost=`echo $ROW | awk '{split($0,a,"|"); print a[4]}'`;
		DestinationHost=`echo $ROW | awk '{split($0,a,"|"); print a[5]}'`;
		SourceDir=`echo $ROW | awk '{split($0,a,"|"); print a[6]}'`;
		DestinationDir=`echo $ROW | awk '{split($0,a,"|"); print a[7]}'`;
		Type=`echo $ROW | awk '{split($0,a,"|"); print a[8]}'`;
		
		
		echo -n "$Id		$Title		$Interval		$SourceHost		$DestinationHost		$SourceDir		$SourceDir		$DestinationDir		$Type";
		# Printing my data
		echo "";
		
		
	done
}


if [[ ! -z $1 ]]; then
	#echo "found argument 1";
	if [[ "$1" == 'list' ]]; then
		echo "Listing Schedules";
		ListSchedules;
	fi
else
	echo "No arguments";
	echo "Help: ";
	echo "list								List schedules";
	exit 1;
fi





