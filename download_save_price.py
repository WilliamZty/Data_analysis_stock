from datetime import datetime, timedelta
from textwrap import dedent
import yfinance as yf
import mysql.connector
from airflow.providers.mysql.operators.mysql import MySqlOperator
import os
# The DAG object; we'll need this to instantiate a DAG
from airflow import DAG

# Operators; we need this to operate!sudo
from airflow.operators.python import PythonOperator

from airflow.utils.dates import days_ago
from airflow.models import Variable

def get_tickers():
    stock_list = Variable.get("stock_list_json", deserialize_json=True)
    
    #stocks = context["dag_run"].conf.get("stocks", None) if("dag_run" in context and context["dag_run"] is not null)

    #if stocks:
    #    stock_list =stocks
    return stock_list
    
def download_prices():
    stock_list =  get_tickers()
    valid_tickers = []
    for ticker in stock_list:
        dat = yf.Ticker(ticker)
        hist = dat.history(period='1mo')

        if hist.shape[0]>0:
            valid_tickers.append(ticker)
        else:
            continue

        with open(get_file_path(ticker), 'w') as writer:
            hist.to_csv(writer, index = True)
        print(f"Downloaded {ticker}")
    return valid_tickers

def get_file_path(ticker):
    return f'/home/zty/airflow/logs/{ticker}.csv'

def load_price_data(ticker):
    with open(get_file_path(ticker),'r') as reader:
        lines = reader.readlines()
        return [[ticker]+line.split(',')[:5] for line in lines if line[:4]!='Date']

def save_to_mysql_stage():
    tickers = get_tickers()

    mydb = mysql.connector.connect(
    host = "localhost",
    user = 'root',
    password = '',
    database = 'demodb',
    port = 3306
    )

    mycursor = mydb.cursor()
    for ticker in tickers:
        val = load_price_data(ticker)
        print(f'{ticker} length={len(val)} {val[1]}')

        sql = '''INSERT INTO stock_prices_stage
            (ticker, as_of_date, open_price, high_price, low_price, close_price)
            VALUES (%s, %s, %s, %s, %s, %s)'''
        mycursor.executemany(sql,val)

        mydb.commit()

        print(mycursor.rowcount,'record inserted.')

default_args = {
    'owner' : 'William'
}

with DAG(
    dag_id = 'download_save_price',
    default_args=default_args,
    description='Download stock price and save to local csv files.',
    schedule_interval=timedelta(days=1),
    start_date=days_ago(2),
    #catchup=False,
    tags=['harrytandata'],
) as dag:

    download_task = PythonOperator(
        task_id = 'download_prices',
        python_callable = download_prices,
        
    )

    save_task = PythonOperator(
        task_id = 'save_to_mysql_stage',
        python_callable = save_to_mysql_stage
    )

    mysql_task = MySqlOperator(
        task_id = 'merge_stock_price',
        mysql_conn_id = 'demodb',
        sql = 'merge_stock_price.sql',
        dag=dag,
    )

    download_task >> save_task >> mysql_task