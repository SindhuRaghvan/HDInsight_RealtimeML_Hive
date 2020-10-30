import pyspark.sql.functions as f
from pyspark.conf import SparkConf
from pyspark.sql import DataFrame
from pyspark.sql.utils import StreamingQueryException
from pyspark.sql.types import *
from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from pyspark.ml import PipelineModel
from pyspark.ml.classification import LogisticRegressionModel
from pyspark.ml.regression import GBTRegressionModel
from pyspark.ml.feature import *
from time import sleep
import json , requests, os

os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-streaming-kafka-0-10_2.11:2.3.0,org.apache.spark:spark-sql-kafka-0-10_2.11:2.3.0 pyspark-shell'

conf = SparkConf()  # create the configuration
conf.set("spark.jars", "abfs://dependency@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/spark-mssql-connector_2.11-1.1.0.jar")  # set the spark.jars
spark = SparkSession.builder.appName("ConsumerKafka").config(conf=conf).getOrCreate()

#Replace the bootstrapservers below...
KafkaBserver="<ENTER-KAFKABROKER-HERE>" #TODO : Replace with the server value copied from the Kafka Server

servername = "jdbc:sqlserver://<SQL_SERVER_HERE>.database.windows.net:1433"
dbname = "Predictions"
url = servername + ";" + "databaseName=" + dbname + ";"
table_name = "UserData"     
username = "sqluser"  #Change the username if you changed it during deployment
password = "<SQL_PWD_HERE>"  


write_file_loc = "abfs://predictions@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/predicted_data/"
check_point_loc= "abfs://predictions@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/checkpoint_data/"
CatModelLoc = "abfs://models@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/CatMod/"; # The last backslash is needed;
IntModelLoc = "abfs://models@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/IntMod/"
PipelineLoc = "abfs://models@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/PipelineMod/"


schema = StructType([ StructField("ID", StringType(), True),
                      StructField("BIRTH", StringType(), True),
                      StructField("AGE", StringType(), True),
                      StructField("HOMEKIDS", StringType(), True),
                      StructField("YOJ", StringType(), True),
                      StructField("INCOME", StringType(), True),
                      StructField("MSTATUS", StringType(), True),
                      StructField("GENDER", StringType(), True),
                      StructField("EDUCATION", StringType(), True),
                      StructField("OCCUPATION", StringType(), True),
                      StructField("TRAVTIME", StringType(), True),
                      StructField("BLUEBOOK", StringType(), True),
                      StructField("TIF", StringType(), True),
                      StructField("CAR_TYPE", StringType(), True),
                      StructField("OLDCLAIM", StringType(), True),
                      StructField("CLM_FREQ", StringType(), True),
                      StructField("MVR_PTS", StringType(), True),
                      StructField("CAR_AGE", StringType(), True)
                      ])   

print("Loading Models....")
PModel = PipelineModel.load(PipelineLoc)  
LRModel = LogisticRegressionModel.load(CatModelLoc)
GBTModel = GBTRegressionModel.load(IntModelLoc)  

if KafkaBserver == "<ENTER-KAFKAZBROKER-HERE>":
    print("Update Kafka server in the file")
    exit()

raw_records = spark.readStream.format("kafka") \
    .option("kafka.bootstrap.servers", KafkaBserver)\
    .option("subscribe", "NewUser") \
    .option("startingOffsets", "latest") \
    .load()


NestedJsonDf=raw_records.select(f.col("key").cast("string"),f.from_json(f.col("value").cast("string"), schema).alias("UserRecord"))
FlatDf = NestedJsonDf.selectExpr("UserRecord.ID", "UserRecord.BIRTH", "UserRecord.AGE","UserRecord.HOMEKIDS", "UserRecord.YOJ","UserRecord.INCOME","UserRecord.MSTATUS","UserRecord.GENDER","UserRecord.EDUCATION","UserRecord.OCCUPATION","UserRecord.TRAVTIME","UserRecord.BLUEBOOK","UserRecord.TIF","UserRecord.CAR_TYPE","UserRecord.OLDCLAIM","UserRecord.CLM_FREQ","UserRecord.MVR_PTS","UserRecord.CAR_AGE")
UserDf = FlatDf.withColumn("time_p", f.current_timestamp())

print("cleaning data...")
UserDf=UserDf.withColumn("INCOME", f.regexp_replace(f.col("INCOME"), "[$#,]", ""))
UserDf=UserDf.withColumn("BLUEBOOK", f.regexp_replace(f.col("BLUEBOOK"), "[$#,]", ""))
UserDf=UserDf.withColumn("OLDCLAIM", f.regexp_replace(f.col("OLDCLAIM"), "[$#,]", ""))


UserDf=UserDf.withColumn("INCOME", f.trim(UserDf.INCOME))
UserDf=UserDf.withColumn("BLUEBOOK", f.trim(UserDf.BLUEBOOK))
UserDf=UserDf.withColumn("OLDCLAIM", f.trim(UserDf.OLDCLAIM))


UserDf=UserDf.withColumn('BIRTH',f.to_date(UserDf['BIRTH'], 'dd-MMM-yy'))
for c in UserDf.columns:
    if c not in ['MSTATUS','GENDER','EDUCATION', 'OCCUPATION', 'CAR_TYPE', 'time_p', 'BIRTH']:
        UserDf=UserDf.withColumn(c,UserDf[c].cast(IntegerType()))

UserDf=UserDf.withColumnRenamed("YOJ","YearsOnJob")\
            .withColumnRenamed("TRAVTIME","Travel_time")\
            .withColumnRenamed("TIF","Time_In_Force")\
            .withColumnRenamed("OLDCLAIM","OLDCLAIM_AMT")\
            .withColumnRenamed("CLM_FREQ","CLAIM_FREQ")

print("Making Transformations....")
TDf = PModel.transform(UserDf)


print("Making predictions....")
crash_pred = LRModel.transform(TDf)
claim_pred = GBTModel.transform(TDf)


print("Collecting final predictions....")
crash_pred = crash_pred.withColumnRenamed("prediction","CRASH_PREDICTION")
claim_pred = claim_pred.withColumnRenamed("prediction","CLAIM_PREDICTION")

crash_pred =crash_pred.select([c for c in UserDf.columns] + ["CRASH_PREDICTION"])
claim_pred =claim_pred.select([c for c in UserDf.columns] + ["CLAIM_PREDICTION"])

FinalDf = crash_pred.join(claim_pred, crash_pred.ID == claim_pred.ID)
FinalDf = FinalDf.select([crash_pred[c] for c in crash_pred.columns] + ["CLAIM_PREDICTION"])

y_udf=f.udf(lambda x, y: 0 if y==0 else x)
FinalDf=FinalDf.withColumn("CLAIM_PRED", y_udf('CLAIM_PREDICTION','CRASH_PREDICTION')).drop("CLAIM_PREDICTION")

y_udf=f.udf(lambda y: "No" if y==0 else "Yes", StringType())
FinalDf=FinalDf.withColumn("CRASH_PRED", y_udf('CRASH_PREDICTION')).drop("CRASH_PREDICTION")

FinalDf=FinalDf.withColumn("CLAIM_PRED", f.round(f.col("CLAIM_PRED"),2))


def batchfunc(df, epoch_id):
     df.write.format("com.microsoft.sqlserver.jdbc.spark") \
     .mode("append") \
     .option("url", url) \
     .option("dbtable", table_name) \
     .option("user", username) \
     .option("password", password) \
     .save()


query1 = FinalDf.writeStream.foreachBatch(batchfunc).start()

query2 = FinalDf.writeStream \
    .format("json") \
    .option("format", "append") \
    .option("path", write_file_loc) \
    .option("checkpointLocation",check_point_loc) \
    .outputMode("append") \
    .option("failOnDataLoss", "false") \
    .start() 

query1.awaitTermination() 
query2.awaitTermination()

  
