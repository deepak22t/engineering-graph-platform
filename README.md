# engineering-graph-platform

echo 'https://deepak22t:YOUR_NEW_TOKEN@github.com' > ~/.git-credentials
chmod 600 ~/.git-credentials
git push -u origin main


 uv pip freeze > requirements.txt

 (.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ docker compose version
docker: unknown command: docker compose

Run 'docker --help' for more information
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ docker-compose version
docker-compose version 1.29.2, build unknown
docker-py version: 5.0.3
CPython version: 3.12.3
OpenSSL version: OpenSSL 3.0.13 30 Jan 2024
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ docker info
Client:
 Version:    29.1.3
 Context:    default
 Debug Mode: false
 Plugins:
  trust: Manage trust on Docker images (Docker Inc.)    
    Version:  29.1.3
    Path:     /usr/libexec/docker/cli-plugins/docker-trust

Server:
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ ls -l /var/run/docker.sock
srw-rw---- 1 root docker 0 Aug  2 18:22 /var/run/docker.sock
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ getent group docker
docker:x:108:
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ sudo systemctl status docker --no-pager
[sudo] password for deepak: 
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-08-02 18:22:42 UTC; 1h 34min ago
TriggeredBy: ● docker.socket
       Docs: https://docs.docker.com
   Main PID: 309 (dockerd)
      Tasks: 13
     Memory: 83.1M ()
     CGroup: /system.slice/docker.service
             └─309 /usr/bin/dockerd -H fd:// --containe…

Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…t"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…t"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…t"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…)"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02….3
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…t"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…n"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…n"
Aug 02 18:22:42 deepak dockerd[309]: time="2026-08-02…k"
Aug 02 18:22:42 deepak systemd[1]: Started docker.ser…e.
Hint: Some lines were ellipsized, use -l to show in full.
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ sudo usermde -aG docker $USER
sudo: usermde: command not found
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ sudo usermod -aG docker $USER
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$ getent group docker
docker:x:108:deepak
(.venv) deepak@deepak:/mnt/c/Desktop/egp/engineering-graph-platform$


docker compose -f infrastructure/compose/docker-compose.yml config

                    PHASE 0
                       │
        ┌──────────────┼──────────────┐
        ↓              ↓              ↓
     Python          Docker        FastAPI
        ✅              ✅              ✅
                       │
             ┌─────────┼─────────┐
             ↓         ↓         ↓
          Postgres   Neo4j      MinIO
             ✅         ✅          ✅
             │
             ↓
       Manual verification
             ✅
             │
             ↓
       Health endpoint
             ✅
             │
             ↓
       Automated tests
             ✅
             │
             ↓
       Failure handling
             ✅
             │
             ↓
   Development configuration
          ⏳ STEP 7
             │
             ↓
       Basic CI checks
          ⏳
             │
             ↓
       PHASE 0 EXIT GATE