# Replace the TODOs with parameters specific to your setup

# imports
from time import sleep
from json import dumps
from kafka import KafkaProducer

from kafka.errors import KafkaError

import sys
import requests
import json
import random
import time
import csv

## Configuration section
## Replace kafkaBrokers
defaultLoops = 1000
kafkaBrokers = ['<BROKER_HERE>'] #TODO: Replace with your Kafka broker endpoint (including port)
kafkaTopic = 'NewUser'
simulator = True
loops = defaultLoops

## Read command line arguments
print ("Records will loop by:", loops)

## notify if simulator is on
if simulator:
	print ("Running in simulated mode")


# Configure Producer
producer = KafkaProducer(bootstrap_servers=kafkaBrokers,key_serializer=lambda k: k.encode('ascii','ignore'),value_serializer=lambda x: dumps(x).encode('utf-8'))

#### Main definition
def main():
	# Send messages
	for x in range(loops):
		## Make a rest call from Python to get streaming data
		responseList = simulatedResponse()
		
		for val in responseList:
			future = producer.send(kafkaTopic, key=val["ID"], value=val)
			response = future.get(timeout=10000) 
			print(val)
			print('')
			print('')	
			sleep(2)
		sleep(2)


## Define simulator method: returns list with artificial stock data 
def simulatedResponse():
	# Empty json request
	responseList = []
	#read the CSV that would produce kafka messages
	with open('files/ClaimInference.csv') as csv_file:
   		csv_reader = csv.reader(csv_file, delimiter=',')
		line_count = 0
		# Create a record for each row in the CSV and add it to the json request
		for row in csv_reader:
			if line_count == 0:
				line_count += 1
			else:
				UserRecord = {
					"ID" : row[0],
					"BIRTH" : row[2],
					"AGE" : row[3],
					"HOMEKIDS" : row[4],
					"YOJ" : row[5],
					"INCOME" : row[6],
					"MSTATUS" : row[9],
					"GENDER" : row[10],
					"EDUCATION" : row[11],
					"OCCUPATION" : row[12],
					"TRAVTIME" : row[13],
					"BLUEBOOK" : row[15],
					"TIF" : row[16],
					"CAR_TYPE" : row[17],
					"OLDCLAIM" : row[19],
					"CLM_FREQ" : row[20],
					"MVR_PTS" : row[22],
					"CAR_AGE" : row[24]
					}
				responseList.append(UserRecord)
	return responseList

def currentMilliTime():
	return int(round(time.time() * 1000))

#### Main execution
main()
