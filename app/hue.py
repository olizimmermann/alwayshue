#!/usr/bin/env python
import requests
import threading
import logging
from typing import Union, List, Optional
from logging.handlers import RotatingFileHandler

# Configure logging
handler = RotatingFileHandler("app.log", maxBytes=10*1024*1024, backupCount=3)  # 10 MB max size, 3 backups
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[handler])

class HueAction:
    def __init__(self, ip: str, token: str, lamps: Optional[List[int]] = None, group: Optional[int] = None):
        self.IP = ip
        self.TOKEN = token
        self.BASE_URL = f'http://{self.IP}/api/{self.TOKEN}/'
        self.LAMPS = lamps
        self.GROUP = group

    def get_group(self) -> Union[dict, bool]:
        """Fetch the current group state from the Hue Bridge."""
        url = f'{self.BASE_URL}groups/{self.GROUP}'
        try:
            r = requests.get(url)
            if r.ok:
                return r.json()
            logging.error(f"Failed to fetch group {self.GROUP}. Status: {r.status_code}")
            return False
        except Exception as e:
            logging.exception(f"Error fetching group {self.GROUP}: {e}")
            return False

    def get_lamp(self, lamp: int) -> Union[dict, bool]:
        """Fetch the current lamp state from the Hue Bridge."""
        url = f'{self.BASE_URL}lights/{lamp}'
        try:
            r = requests.get(url)
            if r.ok:
                return r.json()
            logging.error(f"Failed to fetch lamp {lamp}. Status: {r.status_code}")
            return False
        except Exception as e:
            logging.exception(f"Error fetching lamp {lamp}: {e}")
            return False

    def action_group(self, bri: int = 100) -> dict:
        """Toggle group lights on or off based on current state."""
        url = f'{self.BASE_URL}groups/{self.GROUP}/action'
        group_response = self.get_group()

        if group_response:
            current_state = group_response['action']['on']
            data = '{"on": false}' if current_state else '{"on": true, "bri": 100}'
            success = self.send_put(url, data)
            return {
                'state_old': current_state,
                'state_new': not current_state if success else current_state,
                'group': self.GROUP
            }
        return {'state_old': False, 'state_new': False, 'error': 'No group found'}

    def action_lamp(self, lamp: int, state: Optional[bool] = None, bri: int = 100) -> bool:
        """Toggle lamp state or set it explicitly."""
        url = f'{self.BASE_URL}lights/{lamp}/state/'
        lamp_response = self.get_lamp(lamp) if state is None else {'state': {'on': state}}

        if lamp_response:
            current_state = lamp_response['state']['on']
            new_state = not current_state if state is None else state
            data = '{"on": true, "bri": 254}' if new_state else '{"on": false}'
            return self.send_put(url, data)
        return False

    def send_put(self, url: str, data: str) -> bool:
        """Send a PUT request to the Hue Bridge."""
        try:
            r = requests.put(url, data=data)
            if r.ok:
                return True
            logging.error(f"PUT request failed. Status: {r.status_code}, Response: {r.text}")
            return False
        except Exception as e:
            logging.exception(f"Error sending PUT request to {url}: {e}")
            return False

    def trigger_lamps(self) -> dict:
        """Toggle all lamps' state based on their current state."""
        if not self.LAMPS:
            return {'error': 'No lamps defined'}
        first_lamp_state = self.get_lamp(self.LAMPS[0])['state']['on']
        new_state = not first_lamp_state

        threads = []
        for lamp in self.LAMPS:
            t = threading.Thread(target=self.action_lamp, args=(lamp, new_state))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()

        return {'state_old': first_lamp_state, 'state_new': new_state, 'lamps': self.LAMPS}

    def trigger_lamps_reverse(self) -> dict:
        """Toggle lamps in reverse order based on their current state."""
        if not self.LAMPS:
            return {'error': 'No lamps defined'}
        first_lamp_state = self.get_lamp(self.LAMPS[0])['state']['on']
        new_state = not first_lamp_state
        lamp_order = self.LAMPS[::-1] if first_lamp_state else self.LAMPS

        threads = []
        for lamp in lamp_order:
            t = threading.Thread(target=self.action_lamp, args=(lamp, new_state))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()

        return {'state_old': first_lamp_state, 'state_new': new_state, 'lamps': lamp_order}

    def trigger_group(self) -> dict:
        """Toggle a group of lamps."""
        return self.action_group()
