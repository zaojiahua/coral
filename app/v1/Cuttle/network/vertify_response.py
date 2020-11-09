class VertifyResponse:
    def __init__(self):
        """
        stok_response eg:
            {'id': 1, 'result': {'stok': '7f27fc9b7a4078cec496330d8dd16d25'}, 'error_code': '0'}
        client_response eg:
            {'id': 1, 'result': [
            {'leasetime': '23:55:5', 'name': 'vivo-X23-Magic-color', 'macaddr': 'DC-31-D1-47-4F-93', 'ipaddr': '10.80.5.59', 'interface': 'lan'},
            {'leasetime': '4:30:3', 'name': 'MI9SE-xiaomishouji', 'macaddr': '60-AB-67-F7-16-EB', 'ipaddr': '10.80.5.242', 'interface': 'lan'},
            ], 'error_code': '0'}
        bind_response eg:
            {'id': 1, 'others': {'max_rules': 80}, 'result': {'mac': '52-70-23-2C-1B-C2', 'note': 'HUAWEI_Mate_30-b983a2131a', 'enable': 'on', 'interface': 'LAN', 'ip': '10.80.5.228'}, 'error_code': '0'}
        static_response eg:
            {'id': 1, 'others': {'max_rules': 80}, 'result': [{'mac': '40-D6-3C-0D-D8-0C', 'note': 'TA', 'enable': 'on', 'ip': '10.80.5.110', 'interface': 'LAN'},
            {'mac': '40-D6-3C-0F-B5-94', 'note': 'PA', 'enable': 'on', 'ip': '10.80.5.121', 'interface': 'LAN'},
            {'mac': '40-D6-3C-13-EA-48', 'note': 'TB', 'enable': 'on', 'ip': '10.80.5.111', 'interface': 'LAN'}],
            'error_code': '0'}

        unbind_response eg:
            {'id': 1, 'others': {'max_rules': 80}, 'result': [{'success': True, 'key': 'key-13', 'index': '13'}], 'error_code': '0'}

        :return:
        True -- Correct
        False -- wrong
        """
        pass

    @staticmethod
    def vertify_stok(response_json_data):
        if not VertifyResponse.vertify_key(response_json_data):
            return False
        if 'stok' not in response_json_data['result'].keys():
            return False
        return True

    @staticmethod
    def vertify_client(response_json_data):
        if not VertifyResponse.vertify_key(response_json_data):
            return False
        if len(response_json_data['result']) == 0:
            return False
        return True

    @staticmethod
    def vertify_bind(mac, note, ip, getted_response_json_data):
        know_response_data = {'id': 1, 'others': {'max_rules': 80}, 'result': {'mac': mac, 'note': note, 'enable': 'on', 'interface': 'LAN', 'ip': ip}, 'error_code': '0'}
        if getted_response_json_data != know_response_data:
            return False
        return True

    @staticmethod
    def vertify_static(response_json_data):
        if not VertifyResponse.vertify_key(response_json_data):
            return False
        return True

    @staticmethod
    def vertify_unbind(unbind_ip_index, getted_response_data):
        know_response_json_data = {'id': 1, 'others': {'max_rules': 80}, 'result': [
            {'success': True, 'key': 'key-' + str(unbind_ip_index), 'index': str(unbind_ip_index)}], 'error_code': '0'}
        if getted_response_data != know_response_json_data:
            return False
        return True

    @classmethod
    def vertify_key(cls, json_data):
        # id result error_code
        data_keys = json_data.keys()
        if "id" not in data_keys or 'result' not in data_keys or 'error_code' not in data_keys or json_data['error_code'] != '0':
            return False
        return True
