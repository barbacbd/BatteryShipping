from battery_pickup_service.package_data import PackagingSystem, LocationInformation, DateInformation
from json import loads, dumps
import requests
from logging import getLogger, INFO
import pytest
from os.path import exists

log = getLogger()
log.setLevel(INFO)

info_endpoint = 'http://127.0.0.1:5000/info'
quote_endpoint = 'http://127.0.0.1:5000/quote'
headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

def test_empty_info():
    x = requests.post(info_endpoint)
    assert x.status_code == 400


def test_valid_info_order_id_only():
    x = requests.post(info_endpoint, headers=headers, json={"order_id": 4})
    log.info(x.json())
    assert x.status_code == 200
    assert x.json() is not None


def test_invalid_info_order_id():
    x = requests.post(info_endpoint, headers=headers, json={"order_id": 5})
    assert x.status_code == 200
    assert x.json() is not None
    log.info(x.json())

def test_info_valid_location():
    x = requests.post(
        info_endpoint, headers=headers, 
        json={
            "state": "Virginia",
            "city": "Virginia Beach",
            "street_address": "123 Example Street",
            "zip_code": "12345"
        })
    assert x.status_code == 200
    assert x.json() is not None
    log.info(x.json())


def test_info_valid_location_and_date():
    x = requests.post(
        info_endpoint, headers=headers, 
        json={
            "state": "Virginia",
            "city": "Virginia Beach",
            "street_address": "123 Example Street",
            "zip_code": "12345",
            "day": 20,
            "month": 9,
            "year": 2023
        })
    assert x.status_code == 200
    assert x.json() is not None
    log.info(x.json())


def test_info_valid_location_invalid_date():
    x = requests.post(
        info_endpoint, headers=headers, 
        json={
            "state": "Virginia",
            "city": "Virginia Beach",
            "street_address": "123 Example Street",
            "zip_code": "12345",
            "day": 20,
            "month": 10,
            "year": 2023
        })
    assert x.status_code == 200
    assert x.json() is not None
    log.info(x.json())


def test_info_location_not_found():
    x = requests.post(
        info_endpoint, headers=headers, 
        json={
            "state": "North Carolina",
            "city": "Virginia Beach",
            "street_address": "123 Example Street",
            "zip_code": "12345",
        })
    assert x.status_code == 200
    assert x.json() is not None
    log.info(x.json())


def test_quote_valid_order_id():
    x = requests.get(quote_endpoint, headers=headers, json={"order_id": 4})
    if x.status_code == 200:
        with open("quote.xlsx", 'wb') as returnedFile:
            returnedFile.write(x.content)

    log.info("Check your local directory for your quote.\n\n\n")
    assert exists("quote.xlsx")


def test_setting_quote_acceptance():
    log.info("Test with valid order id - Notice quote is rejected")
    x = requests.post(info_endpoint, headers=headers, json={"order_id": 4})
    log.info(x.json())
    assert x.status_code == 200
    assert x.json() is not None

    log.info("Accept Quote")
    x = requests.post(quote_endpoint, headers=headers, json={"order_id": 4, "accept": True})
    assert x.status_code == 200

    log.info("Test with valid order id - Notice quote is accepted")
    x = requests.post(info_endpoint, headers=headers, json={"order_id": 4})
    log.info(x.json())
    assert x.status_code == 200
    assert x.json() is not None
    assert x.json()["orders"][0]["accepted"] == True

    log.info("Setting to False but the status code is bad")
    x = requests.post(quote_endpoint, headers=headers, json={"order_id": 4, "accept": "sdfasdf"})
    log.info(x.status_code)
    assert x.status_code == 400

    x = requests.post(info_endpoint, headers=headers, json={"order_id": 4})
    log.info(x.json())
    assert x.status_code == 200
    assert x.json() is not None
    assert x.json()["orders"][0]["accepted"] == False

