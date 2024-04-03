#!/usr/bin/bash
# This scripts executes a Turbinia end-to-end test against a local 
# docker-compose Turbinia stack
# The evidence processed is a prepared raw disk image.

# Set default return value
RET=1

echo "Create evidence folder"
mkdir -p ./evidence
sudo chmod 777 ./evidence

echo "==> Copy test artifacts to /evidence"
cp ./test_data/artifact_disk.dd ./evidence/
cp ./turbinia/e2e/e2e-recipe.yaml ./evidence/

echo "==> Startup local turbinia docker-compose stack"
export TURBINIA_EXTRA_ARGS="-d"
docker-compose -f ./docker/local/docker-compose.yml up -d

echo "==> Sleep for 10 seconds to let containers start"
sleep 10

echo "==> Show and check running containers"
containers=( turbinia-server turbinia-worker turbinia-api-server redis )
for container in "${containers[@]}"
do
        docker ps | grep "$container"
        RET=$?
        if [ $RET -ne 0 ]; then
                echo "ERROR: $container container not up, exiting."
                echo "==> Show $container logs"
                docker logs $container
                exit 1
        fi
done
echo "All containers up and running!"

echo "==> Getting the turbinia-api-server container IP address"
API_SERVER=`docker inspect turbinia-api-server | jq '.[].NetworkSettings.Networks.[].IPAddress' | tr -d "\""`
echo "==> Got IP address: $API_SERVER"

echo "==> Generating turbinia-client configuration"
echo '{
  "default": {
        "description": "Local e2e test environment",
        "API_SERVER_ADDRESS": "http://turbinia-api-server",
        "API_SERVER_PORT": 8000,
        "API_AUTHENTICATION_ENABLED": false,
        "CLIENT_SECRETS_FILENAME": ".client_secrets.json",
        "CREDENTIALS_FILENAME": ".credentials.json"
  }
}' | sed s/turbinia-api-server/$API_SERVER/> ./evidence/.turbinia_api_config.json
cat ./evidence/.turbinia_api_config.json

echo "==> Show loop device availability in worker"
docker exec -t turbinia-worker /sbin/losetup -a
docker exec -t turbinia-worker ls -al /dev/loop*

echo "==> Show evidence volume contents in worker"
docker exec -t turbinia-worker ls -al /evidence/

echo "==> Show container logs"
docker logs turbinia-server
docker logs turbinia-worker
docker logs turbinia-api-server

echo "==> Create Turbinia request"
RECIPE_DATA=`cat ./evidence/e2e-recipe.yaml | base64 -w0`
turbinia-client -p ./evidence submit rawdisk --source_path /evidence/artifact_disk.dd --request_id 123456789 --recipe_data {$RECIPE_DATA} 

echo "==> Waiting 5 seconds before polling request status"
sleep 5

echo "==> Polling the API server for request status"
# Wait until request is complete 
req_status=$(turbinia-client -p ./evidence status request 123456789 -j | jq -r '.status')
while [[ $req_status = "running" ]]
do
  req_status=$(turbinia-client -p ./evidence status request 123456789 -j | jq -r '.status')
  if [[ $req_status = "running" ]]
  then
    echo "Turbinia request 123456789 is still running. Sleeping for 15 seconds..."
    sleep 15
  fi
done

echo "==> Check the status of the request"
if [ $req_status != "successful" ]
then
    echo "Request is not running and the status is not successful!"
else
    echo "Request successfully completed"
    RET=0
fi

echo "==> Displaying request status"
turbinia-client -p ./evidence status request 123456789 -j

echo "==> Show Turbinia server logs"
docker logs turbinia-server

echo "==> Show Turbinia worker logs"
docker logs turbinia-worker

echo "==> Show Turbinia API server logs"
docker logs turbinia-api-server

echo "==> Show evidence volume contents in worker"
docker exec -t turbinia-worker ls -al /evidence/
docker exec -t turbinia-worker find /evidence -ls

echo "==> Show PlasoParserTask logs"
for i in cat `docker exec turbinia-server turbiniactl -a status -r 123456789|grep -Eo '*/evidence/123456789/.*PlasoParserTask.*txt'`; do docker exec turbinia-worker cat $i; done

exit $RET
