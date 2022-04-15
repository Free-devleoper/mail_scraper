import datetime
import logging
import requests
import azure.functions as func


def main(mytimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.datetime.utcnow().replace(
        tzinfo=datetime.timezone.utc).isoformat()
    resp=requests.request("GET", "https://aisafetymailscrapper.azurewebsites.net/update_access_token")
    print(resp.status_code)
