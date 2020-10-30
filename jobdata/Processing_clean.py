
import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)
#from pyspark.sql import Row
from pyspark.sql import SQLContext
from pyspark import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.types import *
import datetime
import pyspark.sql.functions as f
from pyspark.ml.classification import LogisticRegression, RandomForestClassifier
from pyspark.ml.regression import LinearRegression, GBTRegressor
from pyspark.ml import Pipeline
from pyspark.ml.feature import *
from pyspark.ml.evaluation import BinaryClassificationEvaluator, RegressionEvaluator

#get SQL context for the current Spark session to run SQL read
spark = SparkSession.builder.appName("BuildModel").getOrCreate()
sc = spark.sparkContext
sqlContext = SQLContext(sc)

# Location of training data
ins_train_file_loc = "abfs://data@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/car_insurance_claim.csv"
# Set model storage directory path. This is where models will be saved.
CatModelLoc = "abfs://models@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/CatMod/"; # The last backslash is needed;
IntModelLoc = "abfs://models@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/IntMod/"
PipelineLoc = "abfs://models@<ADLS GEN2 STORAGE NAME>.dfs.core.windows.net/PipelineMod/"

# Let's make sure that we got the locations correct
print(ins_train_file_loc)

ClaimData = sqlContext.read.csv(ins_train_file_loc, header=True, inferSchema=True)

ClaimData.printSchema()


#Make the data more readable
ClaimData_df=ClaimData.withColumnRenamed("YOJ","YearsOnJob")\
            .withColumnRenamed("TRAVTIME","Travel_time")\
            .withColumnRenamed("TIF","Time_In_Force")\
            .withColumnRenamed("OLDCLAIM","OLDCLAIM_AMT")\
            .withColumnRenamed("CLM_FREQ","CLAIM_FREQ")\
            .withColumnRenamed("CLM_AMT","TARGET_CLAIM") \
            .withColumnRenamed("CLAIM_FLAG","CRASH_FLAG")

#Clean the string data and remove unnecessary characters
ClaimData_df=ClaimData_df.withColumn("INCOME", f.regexp_replace(f.col("INCOME"), "[$#,]", ""))
ClaimData_df=ClaimData_df.withColumn("BLUEBOOK", f.regexp_replace(f.col("BLUEBOOK"), "[$#,]", ""))
ClaimData_df=ClaimData_df.withColumn("OLDCLAIM_AMT", f.regexp_replace(f.col("OLDCLAIM_AMT"), "[$#,]", ""))
ClaimData_df=ClaimData_df.withColumn("TARGET_CLAIM", f.regexp_replace(f.col("TARGET_CLAIM"), "[$#,]", ""))

ClaimData_df=ClaimData_df.withColumn("MSTATUS", f.regexp_replace(f.col("MSTATUS"), "z_", ""))
ClaimData_df=ClaimData_df.withColumn("GENDER", f.regexp_replace(f.col("GENDER"), "z_", ""))
ClaimData_df=ClaimData_df.withColumn("EDUCATION", f.regexp_replace(f.col("EDUCATION"), "[z_<]", ""))
ClaimData_df=ClaimData_df.withColumn("OCCUPATION", f.regexp_replace(f.col("OCCUPATION"), "z_", ""))
ClaimData_df=ClaimData_df.withColumn("CAR_TYPE", f.regexp_replace(f.col("CAR_TYPE"), "z_", ""))

#Trim to remove all extra whitespaces so casting to integer is easy
ClaimData_df=ClaimData_df.withColumn("INCOME", f.trim(ClaimData_df.INCOME))
ClaimData_df=ClaimData_df.withColumn("BLUEBOOK", f.trim(ClaimData_df.BLUEBOOK))
ClaimData_df=ClaimData_df.withColumn("OLDCLAIM_AMT", f.trim(ClaimData_df.OLDCLAIM_AMT))
ClaimData_df=ClaimData_df.withColumn("TARGET_CLAIM", f.trim(ClaimData_df.TARGET_CLAIM))

#Drop all null values from all rows
ClaimData_df = ClaimData_df.na.drop()

#Let's adjust the datatypes to make sure we assign the right dayatypes
ClaimData_df=ClaimData_df.withColumn('INCOME',ClaimData_df["INCOME"].cast(IntegerType()))
ClaimData_df=ClaimData_df.withColumn('BLUEBOOK',ClaimData_df["BLUEBOOK"].cast(IntegerType()))
ClaimData_df=ClaimData_df.withColumn('OLDCLAIM_AMT',ClaimData_df["OLDCLAIM_AMT"].cast(IntegerType()))
ClaimData_df=ClaimData_df.withColumn('TARGET_CLAIM',ClaimData_df["TARGET_CLAIM"].cast(IntegerType()))
ClaimData_df=ClaimData_df.withColumn('CRASH_FLAG',ClaimData_df["CRASH_FLAG"].cast(IntegerType()))


#describe the numeric data to find any anomalies
numeric_features=[t[0] for t in ClaimData_df.dtypes if t[1]== 'int']
ClaimData_df.select(numeric_features).describe().toPandas().transpose()

#Let's drop that row that shows has negative car age
ClaimData_df=ClaimData_df.where(ClaimData_df.CAR_AGE!=-3)


y_udf=f.udf(lambda y: "No" if y==0 else "Yes", StringType())
new_df=ClaimData_df.withColumn("CRASH_FLAGG", y_udf('CRASH_FLAG')).drop("CRASH_FLAG")
ClaimData_df.checkpoint

new_df=new_df.withColumnRenamed("CRASH_FLAGG","CRASH_FLAG")

numeric_features=[t[0] for t in new_df.dtypes if t[1]== 'int']
Categoric_features=[t[0] for t in new_df.dtypes if t[1]== 'string']
print(Categoric_features)
print(numeric_features)

#Remove the target fields from feature list
numeric_features.remove('TARGET_CLAIM')
Categoric_features.remove('CRASH_FLAG')
#Also remove the features that we know are too unique to make a difference
Categoric_features.remove('BIRTH')
numeric_features.remove('ID')

stages = []

for categoricalCol in Categoric_features:
    stringIndexer = StringIndexer() \
                    .setInputCol (categoricalCol) \
                    .setOutputCol (categoricalCol + '_Index') \
                    .setHandleInvalid ("skip")
    stages += [stringIndexer]
        


for categoricalCol in Categoric_features:
    encoder = OneHotEncoderEstimator() \
                .setInputCols ([categoricalCol + '_Index']) \
                .setOutputCols ([categoricalCol + "classVec"])
    stages += [encoder]
    

label_stringIdx = StringIndexer(inputCol = 'CRASH_FLAG', outputCol = 'label')
stages += [label_stringIdx]

assemblerInputs = [c + "classVec" for c in Categoric_features] + numeric_features

assembler = VectorAssembler()\
            .setInputCols(assemblerInputs) \
            .setOutputCol("vec_features") 
stages += [assembler]

scaler = StandardScaler()\
         .setInputCol("vec_features") \
         .setOutputCol("features") 
stages += [scaler]

pipeline = Pipeline(stages = stages)
pipelineModel = pipeline.fit(new_df)

testdf=pipelineModel.transform(new_df)

pipelineModel.write().overwrite().save(PipelineLoc)

#split the rows into 70% training and 30% testing sets
splits=testdf.randomSplit([0.7, 0.3], 2018)

train_df=splits[0]
test_df=splits[1]

#use Binomial Logistic regression to predict "CRASH_FLAG"

lr = LogisticRegression(featuresCol= 'features', labelCol='label', maxIter=10)
# Fit the model
lrModel = lr.fit(train_df)


#run the model to predict and measure the accuracy of model
predictions=lrModel.transform(test_df)
predictions.select('label','features','rawPrediction','prediction','probability').toPandas().head(5)

evaluator = BinaryClassificationEvaluator()
print('Test Area Under ROC', evaluator.evaluate(predictions))

#Use random forest classifiers to predict CRASH_FLAG
RF = RandomForestClassifier(featuresCol = 'features', labelCol = 'label')
rfModel = RF.fit(train_df)
predictions_rf = rfModel.transform(test_df)
predictions_rf.select('label', 'features','rawPrediction', 'prediction', 'probability').show(10)

print('Test Area Under ROC', evaluator.evaluate(predictions_rf))

tempdf = testdf.filter(testdf.CRASH_FLAG=="Yes")

splits=tempdf.randomSplit([0.7, 0.3], 2018)
train_df=splits[0]
test_df=splits[1]

#Run Linear Regression to predict 'TARGET_CLAIM'
claims = LinearRegression(featuresCol='features', labelCol='TARGET_CLAIM', maxIter=5, regParam=0.3)
claim_model = claims.fit(train_df)


claim_pred = claim_model.transform(test_df)
claim_pred.select('CRASH_FLAG','TARGET_CLAIM','features','prediction').show()

regevaluator = RegressionEvaluator()
print('Test Area Under ROC', regevaluator.evaluate(claim_pred))

gbt = GBTRegressor(featuresCol='features', labelCol='TARGET_CLAIM', maxIter=5)
gbt_model = gbt.fit(train_df)
gbt_predictions = gbt_model.transform(test_df)
gbt_predictions.select('prediction', 'TARGET_CLAIM', 'features').show(5)

print('Test Area Under ROC', regevaluator.evaluate(gbt_predictions))

#Persist the model to the containers to use them later
lrModel.write().overwrite().save(CatModelLoc)
gbt_model.write().overwrite().save(IntModelLoc)
