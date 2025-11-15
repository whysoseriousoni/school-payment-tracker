# school-payment-tracker
Small scale application to track "Payment details of students" specially made for school.


# Requirements from client
1. Fees paid by student
   1. Tuition Fee (30000 / Student) [May vary by class]
      1. by month (12 month)
      2. Possibilities for multi pay in a month
   2. Van fee
2. Track Student details
3. Excel reports
   1. Monthly export (Only paid & all)
   2. Financial report (April to March)
   3. School operation report (June to May)
   4. Custom report
   5. Data filter option
4. Backup and Restore
   1. Weekly backup
   2. On-demand backup
   3. On-demand restore

## Setup and Deployment Optionsw
1. Single system host
2. Docker containerization?
### Application stack
1. python=3.10.9
2. Streamlit
3. Database: Sqlite
4. 

## Backup option
Complete backup of database to excel (one file - multiple sheet)

### Methods:
1. Email
2. Local save

## Restore option
Load the excel file (one file - multiple sheets)


