echo "Installing required packages..."
sudo apt install jq
sudo pip install kafka-python
sudo apt-get install python-requests

echo "Enter your Kafka Cluster password:"
read password

echo "Collecting Kafka Cluster information..."
export clusterName=$(curl -u admin:$password -sS -G "http://headnodehost:8080/api/v1/clusters" | jq -r '.items[].Clusters.cluster_name')
export KAFKAZKHOSTS=$(curl -sS -u admin:$password -G https://$clusterName.azurehdinsight.net/api/v1/clusters/$clusterName/services/ZOOKEEPER/components/ZOOKEEPER_SERVER | jq -r '["\(.host_components[].HostRoles.host_name):2181"] | join(",")' | cut -d',' -f1,2);
export KAFKABROKERS=$(curl -sS -u admin:$password -G https://$clusterName.azurehdinsight.net/api/v1/clusters/$clusterName/services/KAFKA/components/KAFKA_BROKER | jq -r '["\(.host_components[].HostRoles.host_name):9092"] | join(",")' | cut -d',' -f1,2);

echo "Creating Kafka Topic...."
/usr/hdp/current/kafka-broker/bin/kafka-topics.sh --create --replication-factor 3 --partitions 8 --topic NewUser --zookeeper $KAFKAZKHOSTS

arrIN=(${KAFKABROKERS//,/ })

echo "Updating producer file..."
sed -i -e 's/<BROKER_HERE>/'$arrIN'/g' files/producer-simulator.py

echo "Copy the following Kafka broker to paste into the consumer file:"
echo $arrIN

