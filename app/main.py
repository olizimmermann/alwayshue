from fastapi import FastAPI, HTTPException, Depends, Request
import os
import logging
import hue
from logging.handlers import RotatingFileHandler

app = FastAPI(title="Hue API", description="Control Philips Hue lights", version="0.1.1")

# Configure logging
handler = RotatingFileHandler("app.log", maxBytes=10*1024*1024, backupCount=3)  # 10 MB max size, 3 backups
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[handler])

# Retrieve environment variables
API_KEY = os.getenv("apikey")
IP = os.getenv("ip")
ALLOWED_HOSTS = os.getenv("allowed_hosts", "*").split(",")
ALLOWED_HOSTS = ["*"] if "*" in ALLOWED_HOSTS else ALLOWED_HOSTS

if not API_KEY or not IP:
    raise RuntimeError("Environment variables 'apikey' and 'ip' must be set!")

# Initialize Hue rooms and groups

#### Room section ####
room_1 = hue.HueAction(lamps=[22, 29, 27, 28, 17, 20, 18, 19, 16, 30, 15, 21, 24, 23], ip=IP, token=API_KEY)
room_2 = hue.HueAction(lamps=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14], ip=IP, token=API_KEY)

rooms = {1: room_1, 2: room_2} # add more rooms as needed

#### Group section ####
group_1 = hue.HueAction(group=1, ip=IP, token=API_KEY)

groups = {1: group_1} # add more groups as needed

#### Middleware section ####

# Middleware to ensure valid environment variables
def verify_env_vars():
    if not API_KEY or not IP:
        raise HTTPException(status_code=500, detail="Missing environment variables: 'apikey' or 'ip'")

# Check if the request's IP is allowed
def is_host_allowed(src_ip: str):
    if src_ip not in ALLOWED_HOSTS and ALLOWED_HOSTS != ["*"]:
        logging.warning(f"Unauthorized access attempt from {src_ip}")
        raise HTTPException(status_code=403, detail="Forbidden - Host not allowed")

# Dynamic room and group handlers
@app.get("/room/{room_id}")
def control_room(room_id: int, request: Request, verify: None = Depends(verify_env_vars)):
    src_ip = request.client.host
    is_host_allowed(src_ip)

    
    room = rooms.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    logging.info(f"Room {room_id} triggered by {src_ip}")
    return room.trigger_lamps()

@app.get("/group/{group_id}")
def control_group(group_id: int, request: Request, verify: None = Depends(verify_env_vars)):
    src_ip = request.client.host
    is_host_allowed(src_ip)

    group = groups.get(group_id) 
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    logging.info(f"Group {group_id} triggered by {src_ip}")
    return group.trigger_group()
