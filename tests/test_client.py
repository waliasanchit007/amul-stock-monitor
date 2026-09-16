import unittest
from unittest.mock import patch
from amul_client import AmulClient, CheckError


class StoreSelection(unittest.TestCase):
    def test_malformed_store_value_is_a_monitoring_error(self):
        replies = ['', 'session = {"tid":"anonymous-test"}',
                   '{"records":[{"pincode":"122001","substore":{}}]}']
        with AmulClient() as client, patch.object(client,'request',side_effect=replies):
            with self.assertRaises(CheckError): client.select_pin('122001')

    def test_missing_selected_store_is_a_monitoring_error(self):
        replies = ['', 'session = {"tid":"anonymous-test"}',
                   '{"records":[{"pincode":"122001","substore":"haryana"}]}',
                   'Updated successfully', 'session = {"tid":"anonymous-test","substore":null}']
        with AmulClient() as client, patch.object(client,'request',side_effect=replies):
            with self.assertRaises(CheckError): client.select_pin('122001')

    def test_wrong_store_must_not_establish_delivery(self):
        replies = ['', 'session = {"tid":"anonymous-test"}',
                   '{"records":[{"pincode":"122001","substore":"haryana"}]}',
                   'Updated successfully', 'session = {"tid":"anonymous-test","substore":{"alias":"delhi","_id":"wrong"}}']
        with AmulClient() as client, patch.object(client,'request',side_effect=replies):
            with self.assertRaises(CheckError): client.select_pin('122001')

    def test_other_pin_must_not_establish_delivery(self):
        replies = ['', 'session = {"tid":"anonymous-test"}',
                   '{"records":[{"pincode":"122010","substore":"haryana"}]}']
        with AmulClient() as client, patch.object(client,'request',side_effect=replies):
            with self.assertRaises(CheckError): client.select_pin('122001')
