import json
import requests
import sys
import boto3

class CerberusClient(object):
    HEADERS = {"Content-Type": "application/json"}

    def __init__(self, username=None, password=None, cerberus_url):
        self.cerberus_url = cerberus_url
        self.username = username
        self.password = password
        self.token = None
        self.set_token()

    def set_token(self):
        """sets client token from Cerberus"""
        auth_resp = self.get_auth()
        if auth_resp['status'] == 'mfa_req':
            token_resp = self.get_mfa(auth_resp)
        else:
            token_resp = auth_resp
        token = token_resp['data']['client_token']['client_token']
        self.token = token

    def get_token(self):
        """Returns a client token from Cerberus"""
        return self.token

    def get_auth(self):
        """Returns auth respose which has client token unless MFA is required"""
        auth_resp = requests.get(self.cerberus_url + '/v2/auth/user',
                                 auth=(self.username, self.password))
        auth_resp_json = json.loads(auth_resp.text)
        if auth_resp.status_code != 200:
           auth_resp.raise_for_status()
        return auth_resp_json

    def get_aws_auth(self):
        """FINISH THIS"""
        account_id = boto3.client('sts').get_caller_identity().get('Account')
        role_name = boto3.client('sts').get_caller_identity().get('Arn').split('/')[1]
        # get the region - couldn't figure out how to do this with boto3
        response = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document')
        region = json.loads(response.text)['region']

    def get_iam_role_token(self):
        """FINISH THIS"""
        request_body = {
            'account_id': account_id,
            'role_name': name,
            'region': region
        }
        encrypted_resp = requests.post(self.cerberus_url + '/v1/auth/iam-role', data=json.dumps(request_body))
        encrypted_resp_json = json.loads(encrypted_resp.text)
        if encrypted_resp.status_code != 200:
           encrypted_resp.raise_for_status()

        auth_data = encrypted_resp_json['auth_data']

        client = boto3.client('kms', region_name=region)

        response = client.decrypt(
            CiphertextBlob=base64.decodebytes(bytes(auth_data, 'utf-8'))
        )

        token = json.loads(response['Plaintext'].decode('utf-8'))['client_token']
        return token

    def get_mfa(self, auth_resp):
        """Gets MFA code from user and returns response which includes the client token"""
        # TODO check if there is more than 1 device.
        # currently cerberus only support Google Authenicator
        sec_code = input('Enter ' + auth_resp['data']['devices'][0]['name'] + ' security code: ')
        mfa_resp = requests.post(self.cerberus_url + '/v2/auth/mfa_check',
                                json={'otp_token': sec_code,
                                      'device_id': auth_resp['data']['devices'][0]['id'],
                                      'state_token': auth_resp['data']['state_token']},
                                       headers=self.HEADERS)
        mfa_resp_json = json.loads(mfa_resp.text)
        if mfa_resp.status_code != 200:
            mfa_resp.raise_for_status()
        return mfa_resp_json

    def get_sdb_path(self,sdb):
        """Returns the path for a SDB"""
        id = self.get_sdb_id(sdb)
        sdb_resp = requests.get(self.cerberus_url + '/v1/safe-deposit-box/' + id + '/',
                                headers={'Content-Type' : 'application/json', 'X-Vault-Token': self.token})
        sdb_resp_json = json.loads(sdb_resp.text)
        if sdb_resp.status_code != 200:
            sdb_resp.raise_for_status()
        path = sdb_resp_json['path']
        return path

    def get_sdb_keys(self,path):
        """Returns the keys for a SDB, which are need for the full vault path"""
        list_resp = requests.get(self.cerberus_url + '/v1/secret/' + path + '/?list=true',
                                headers= {'Content-Type' : 'application/json', 'X-Vault-Token': self.token})
        list_resp_json = json.loads(list_resp.text)
        if list_resp.status_code != 200:
            list_resp.raise_for_status()
        return list_resp_json['data']['keys']

    def get_sdb_id(self,sdb):
        """ Return the ID for the given safety deposit box"""
        sdb_resp = requests.get(self.cerberus_url + '/v1/safe-deposit-box',
                                headers= {'Content-Type' : 'application/json', 'X-Vault-Token': self.token})
        sdb_resp_json = json.loads(sdb_resp.text)
        if sdb_resp.status_code != 200:
            sdb_resp.raise_for_status()
        for r in sdb_resp_json:
            if r['name'] == sdb:
                return str(r['id'])
        print("ERROR: " + sdb + " not found")
        sys.exit(2)

    def get_secret(self,vault_path,key):
        """Returs the secret based on the vault_path and key"""
        secret_resp = requests.get(self.cerberus_url + '/v1/secret/' + vault_path,
                                  headers={'Content-Type' : 'application/json', 'X-Vault-Token': self.token})
        secret_resp_json = json.loads(secret_resp.text)
        if secret_resp.status_code != 200:
            secret_resp.raise_for_status()
        if key in secret_resp_json['data']:
            return secret_resp_json['data'][key]
        else:
            print("ERROR: key " + key + " not found")
            sys.exit(2)
