from fastapi import FastAPI, HTTPException, Depends, Request
import os
import hue

app = FastAPI()

# Retrieve environment variables
API_KEY = os.getenv("apikey") 
IP = os.getenv("ip") # ip address of hue bridge
ALLOWED_HOSTS = os.getenv("allowed_hosts", "*").split(",")

if not API_KEY or not IP:
    raise RuntimeError("Environment variables 'apikey' and 'ip' must be set!")


room_1 = hue.HueAction(lamps=[22,29,27,28,17,20,18,19,16,30,15,21,24,23], ip=IP, token=API_KEY)
room_2 = hue.HueAction(lamps=[1,2,3,4,5,6,7,8,9,10,11,12,13,14], ip=IP, token=API_KEY)

group_1 = hue.HueAction(group=1, ip=IP, token=API_KEY)


# Middleware to ensure API_KEY and IP are configured
def verify_env_vars():
    if not API_KEY or not IP:
        raise HTTPException(status_code=500, detail="Missing environment variables: 'apikey' or 'ip'")

# single lamps
@app.get("/room_1")
def get_room_1(request: Request, verify: bool = Depends(verify_env_vars)):
    src_ip = request.client.host
    if src_ip not in ALLOWED_HOSTS and ALLOWED_HOSTS != "*":
        raise HTTPException(status_code=403, detail="Forbidden - Host is not allowed to trigger livingroom")
    return room_1.trigger_lamps()

@app.get("/room_2")
def get_room_2(request: Request, verify: bool = Depends(verify_env_vars)):
    src_ip = request.client.host
    if src_ip not in ALLOWED_HOSTS and ALLOWED_HOSTS != "*":
        raise HTTPException(status_code=403, detail="Forbidden - Host is not allowed to trigger bedroom")
    return room_2.trigger_lamps()

# groups
@app.get("/group_1")
def get_group_1(request: Request, verify: bool = Depends(verify_env_vars)):
    src_ip = request.client.host
    if src_ip not in ALLOWED_HOSTS and ALLOWED_HOSTS != "*":
        raise HTTPException(status_code=403, detail="Forbidden - Host is not allowed to trigger livingroom")
    return group_1.trigger_group()

# just add more for more rooms or groups