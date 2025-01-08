#!/usr/bin/env python
#
# turn on or off hue groups
#
#
#
import requests
import threading


class HueAction:

    def __init__(self, ip, token, lamps=None, group=None):
        self.IP = ip
        self.TOKEN = token
        self.BASE_URL = 'http://{0}/api/{1}/'.format(self.IP, self.TOKEN)
        self.LAMPS = lamps
        self.GROUP = group

    def get_group(self):
        """
        Get current group state from hue bridge.
        params:
            group: [str] number of group
        return:
            if successful: [json] Data of group
            if unsuccessful: [boolean] False
        """
        url = '{0}groups/{1}'.format(self.BASE_URL, self.GROUP)
        # data = '{"on":false, "bri" : 100}'.format(resource)

        try:
            r = requests.get(url)
            if r.ok:
                response = r.json()
                return response
            return False
        except Exception as e:
            return False


    def get_lamp(self, lamp):
        """
        Get current lamp state from hue bridge.
        params:
            lamp: [str] number of group
        return:
            if successful: [json] Data of group
            if unsuccessful: [boolean] False
        """
        url = '{0}lights/{1}'.format(self.BASE_URL, lamp)
        # data = '{"on":false, "bri" : 100}'.format(resource)

        try:
            r = requests.get(url)
            if r.ok:
                response = r.json()
                return response
            return False
        except Exception as e:
            return False


    def action_group(self, bri=100):
        """
        changes light to on or off. depends of previous state
        params:
            group: [str] number of group
            bri: [int] number of brightness
        returns
            if successful: [boolean] True
            if unsuccessful: [boolean] False
        """
        url = '{0}groups/{1}/action'.format(self.BASE_URL, self.GROUP)
        group_response = self.get_group(self.GROUP)

        if group_response is not False:
            if group_response['action']['on'] == False:
                data = '{"on":true, "bri" : 100}'
                if self.send_put(url, data):
                    return {'state_old': False, 'state_new': True, 'group': self.GROUP}
                else:
                    return {'state_old': False, 'state_new': False, 'error': 'Could not send put request'}

            elif group_response['action']['on'] == True:
                data = '{"on":false, "bri" : 100}'
                if self.send_put(url, data):
                    return {'state_old': True, 'state_new': False, 'group': self.GROUP}
                else:
                    return {'state_old': False, 'state_new': False, 'error': 'Could not send put request'}
        else:
            return {'state_old': False, 'state_new': False, 'error': 'No group found'}


    def action_lamp(self, lamp, nr, state=None, bri=100):
        """
        changes light to on or off. depends of previous state
        params:
            lamp: [str] number of lamp
            bri: [int] number of brightness
        returns
            if successful: [boolean] True
            if unsuccessful: [boolean] False
        """
        url = '{0}lights/{1}/state/'.format(self.BASE_URL, lamp)
        if state is None:
            lamp_response = self.get_lamp(lamp)
        else:
            lamp_response = {'state' : {'on': state}}
        
        if lamp_response is not False:

            if lamp_response['state']['on'] == False:
                data = '{"on":true, "bri": 254, "hue": 8895,"sat": 89}'
                if self.send_put(url, data):
                    return True
                else:
                    return False

            elif lamp_response['state']['on'] == True:
                data = '{"on":false, "bri": 100}'
                if self.send_put(url, data):
                    return True
                else:
                    return False


    def send_put(self, url, data):
        """
        sends put/post request to hue
        params:
            url: [str] api call address
            data: [str] body
        returns
            if successful: [boolean] True
            if unsuccessful: [boolean] False
        """
        try:
            r = requests.put(url, data=data)
            if r.ok:
                response = r.json()
                return True
            return False
        except Exception as e:
            return False

    def trigger_lamps(self):
        ret = self.get_lamp(self.LAMPS[0])
        if ret['state']['on'] == True:
            state = True
        else:
            state = False
        threads = []
        for nr,lamp in enumerate(self.LAMPS):
            t = threading.Thread(target=self.action_lamp, args=(lamp,nr,state,))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()

        return {'state_old': state, 'state_new': not state, 'lamps': self.LAMPS}
        

    def trigger_lamps_reverse(self):
        state = False
        ret = self.get_lamp(self.LAMPS[0])
        if ret['state']['on'] == True:
            LAMPS = self.LAMPS[::-1] # reverse list for better effect, make sure the order is in line with the physical setup
            state = True
        else:
            LAMPS = self.LAMPS
        
        threads = []
        for nr,lamp in enumerate(LAMPS):
            t = threading.Thread(target=self.action_lamp, args=(lamp,nr,state,))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
        
        return {'state_old': state, 'state_new': not state, 'lamps': LAMPS}
    
    def trigger_group(self):
        return self.action_group()