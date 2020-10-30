
echo "Enter Blob Storage Name:"
read Blobname
echo "Enter DataLake Name:"
read ADLSName
echo "Enter Kafka cluster name:"
read KafkaName
echo "Enter Spark cluster name:"
read SparkName
echo "Enter SQL Server Name here:"
read SQLServer
echo "Enter SQL password here:"
read SQLpwd

echo "Updating files with storage names..."
sed -i -e 's/<ADLS GEN2 STORAGE NAME>/'$ADLSName'/g' ./jobdata/Processing_clean.py
sed -i -e 's/<ADLS GEN2 STORAGE NAME>/'$ADLSName'/g' ./Scripts/consumer.py
sed -i -e 's/<SQL_PWD_HERE>/'$SQLpwd'/g' ./Scripts/consumer.py
sed -i -e 's/<SQL_SERVER_HERE>/'$SQLServer'/g' ./Scripts/consumer.py

echo "Uploading to blob..."
az storage blob upload --account-name $Blobname \
    --container-name data --file Data/car_insurance_claim.csv \
    --name car_insurance_claim.csv

echo "Setting up ADLS..."
az storage blob upload-batch -d adfjobs \
    --account-name $ADLSName -s jobdata/

az storage fs directory create -n jars \
 -f adfjobs --account-name $ADLSName 

az storage fs directory create -n logs \
 -f adfjobs --account-name $ADLSName 

az storage fs directory create -n files \
 -f adfjobs --account-name $ADLSName 

az storage fs directory create -n pyFiles \
 -f adfjobs --account-name $ADLSName 

az storage fs directory create -n archives \
 -f adfjobs --account-name $ADLSName 

echo "Uploading to ADLS..."
az storage blob upload --account-name $ADLSName \
    --container-name dependency --file Scripts/spark-mssql-connector_2.11-1.1.0.jar \
    --name spark-mssql-connector_2.11-1.1.0.jar

echo "Transfering files to Kafka and Spark servers...."
scp -r kafkafiles/ sshuser@$KafkaName-ssh.azurehdinsight.net:files/
scp Scripts/consumer.py sshuser@$SparkName-ssh.azurehdinsight.net:consumer.py
scp Scripts/sparkinstall.sh sshuser@$SparkName-ssh.azurehdinsight.net:sparkinstall.sh



