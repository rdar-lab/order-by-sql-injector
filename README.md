# SQL Injection Blind Order-By Data Extractor

## Intro

This is a small POC code to extract data from order-by blind SQL injection. \
This tool was tested with a server connecting into a PSQL database.


The methods that are used are described here: \
https://pulsesecurity.co.nz/articles/postgres-sqli \
https://www.onsecurity.io/blog/pentesting-postgresql-with-sql-injections/

## Usage

1. Update the `config.json` file with the necessary details, look at the code from more options
2. Run 
    > pip install -r requirements.txt
3. To start the data extraction, run:
    > python extract_data.py