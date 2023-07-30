#!/bin/bash
echo "Syncing Pythonanywhere data to local machine"
echo "Local Machine = ubuntu1700"
scac="$1"
SCAC=${scac^^}
echo $scac
echo $SCAC

if [ $1 = 'oslm' ]
then
	backup="oslbackup$(date +%s).sql"
	echo "Backup mysql dump is: $backup"
	excom="mysqldump --no-tablespaces -u nixonai -h nixonai.mysql.pythonanywhere-services.com 'nixonai\$osl'  > $backup"
fi

if [ $1 = 'fela' ]
then
	backup="felbackup$(date +%s).sql"
	echo "Backup mysql dump is: $backup"
	excom="mysqldump --no-tablespaces -u nixonai -h nixonai.mysql.pythonanywhere-services.com 'nixonai\$fel'  > $backup"
fi

if [ $1 = 'nevo' ]
then
	backup="nevbackup$(date +%s).sql"
	echo "Backup mysql dump is: $backup"
	excom="mysqldump --no-tablespaces -u nixonai -h nixonai.mysql.pythonanywhere-services.com 'nixonai\$nev'  > $backup"
fi	
			
pass='Birdie$10'
ssh nixonai@ssh.pythonanywhere.com $excom
echo "mysql dump has been created at python anywhere home directory"

scp nixonai@ssh.pythonanywhere.com:/home/nixonai/$backup /home/mark/databases
echo "mysql dump $backup has been downloaded to /home/mark/databases"

if [ $1 = 'oslm' ]
then
	mysql -h localhost -u root -p$pass osl8 < /home/mark/databases/$backup
fi

if [ $1 = 'fela' ]
then
	mysql -h localhost -u root -p$pass fel8 < /home/mark/databases/$backup
fi

if [ $1 = 'nevo' ]
then
	mysql -h localhost -u root -p$pass nev < /home/mark/databases/$backup
fi
	
echo "local database has been restored to $backup"		
echo "Now sync the data files that are excluded from github from pythonanywhere to local machine"

rsync -avzhe ssh "nixonai@ssh.pythonanywhere.com:/home/nixonai/$scac/webapp/static/$SCAC/data" "/home/mark/flask/nixonai/webapp/static/$SCAC"
rsync -avzhe ssh "nixonai@ssh.pythonanywhere.com:/home/nixonai/$scac/webapp/static/$SCAC/processing" "/home/mark/flask/nixonai/webapp/static/$SCAC"
echo "All necessary files have been synced"
