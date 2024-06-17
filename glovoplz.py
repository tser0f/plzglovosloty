import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import schedule
from discord_webhook import DiscordEmbed, DiscordWebhook
from schedule import every, repeat, run_pending

###############################################################################
## Konfiguracja
##
DWEBHOOK = ""  # URL do webhooka Discord
GUSER = ""  # Użytkownik glovo courier (email)
GPASSWORD = ""  # hasło do glovo
CITY_CODE = ""  # kod miasta glovo - 3 duze litery np WAW

INSTALLATION_GUID = str(
    uuid.uuid4()
).upper()  # (opcjonalnie) GUID instalacji glovo - można wyciągnać przez mitmproxy
SESSION_GUID = str(uuid.uuid4()).upper()  # (opcjonalnie) GUID sesji glovo
# DEVICE_ID = ""
TOKEN_FILE = (
    "token.json"  # plik w ktorym program zapisuje tymczasowy token do logowania w API
)

INTERVAL_SECONDS = 30  # ilość sekund między ponownym sprawdzeniem kalendarza

hours_wanted = [
    (11, 20)
]  # grupy od -> do, np [(10, 12), (15, 17)] to znaczy od 10:00 do 12:00 i od 15:00 do 17:00

##
###############################################################################
notif_hour = datetime.now().hour
slots_notified = []


def datetime_from_utc_to_local(utc_datetime):
    now = datetime.now()
    # offset = datetime.fromtimestamp(now) - datetime.fromtimestamp(now, pytz.UTC)
    offset = now.replace(tzinfo=timezone.utc) - now.astimezone(timezone.utc)
    return utc_datetime - offset


def glovo_headers(authorization=None):
    headers = {
        "user-agent": "Glover/16956 CFNetwork/1496.0.7 Darwin/23.5.0",
        "glovo-location-city-code": CITY_CODE,
        "glovo-client-info": "iOS-courier/2.230.0-16956-Production",
        "glovo-device-osversion": "17.5.1",
        "glovo-language-code": "en",
        # "glovo-device-id": DEVICE_ID,
        "glovo-request-id": str(uuid.uuid4()).upper(),
        "glovo-app-build": "16956",
        "glovo-app-type": "courier",
        "glovo-app-development-state": "Production",
        "glovo-dynamic-session-id": SESSION_GUID,
        "glovo-request-ttl": "120000",
        "accept-language": "en",
        "glovo-api-version": "8",
        "glovo-app-platform": "iOS",
        "accept": "application/json",
        "content-type": "application/json",
        "glovo-installation-id": INSTALLATION_GUID,
        "glovo-app-version": "2.230.0",
    }

    if authorization is not None:
        headers["authorization"] = authorization

    return headers


def g_oauth_refresh(refreshToken):
    json_data = {
        "refreshToken": refreshToken,
    }

    response = requests.post(
        "https://api.glovoapp.com/oauth/refresh",
        headers=glovo_headers(),
        json=json_data,
    )

    return response.json()


def g_oauth_newtoken(username, password):
    json_data = {
        "username": username,
        "grantType": "password",
        "password": password,
        "termsAndConditionsChecked": False,
        "userType": "courier",
    }

    response = requests.post(
        "https://api.glovoapp.com/oauth/token", headers=glovo_headers(), json=json_data
    )
    return response.json()


def g_oauth_token():
    oauth_token_json = {}

    if not Path(TOKEN_FILE).is_file():
        with open(TOKEN_FILE, "w") as f:
            oauth_token_json = g_oauth_newtoken(GUSER, GPASSWORD)
            oauth_token_json["expiration_dt"] = (
                datetime.now() + timedelta(seconds=oauth_token_json["expiresIn"])
            ).timestamp()
            f.write(json.dumps(oauth_token_json, default=str))
            return oauth_token_json["accessToken"]

    with open(TOKEN_FILE, "r") as f:
        oauth_token_json = json.load(f)
        expiration = datetime.fromtimestamp(oauth_token_json["expiration_dt"])
        if expiration > datetime.now():
            return oauth_token_json["accessToken"]

    oauth_token_json = g_oauth_refresh(oauth_token_json["refreshToken"])
    if "expiresIn" not in oauth_token_json:
        Path(TOKEN_FILE).unlink()
        return g_oauth_token()

    oauth_token_json["expiration_dt"] = (
        datetime.now() + timedelta(seconds=oauth_token_json["expiresIn"])
    ).timestamp()

    with open(TOKEN_FILE, "wt") as f:
        f.write(json.dumps(oauth_token_json, default=str))

    return oauth_token_json["accessToken"]


def g_calendar():
    response = requests.get(
        "https://api.glovoapp.com/v4/scheduling/calendar",
        headers=glovo_headers(g_oauth_token()),
    )

    # TODO: remove this
    with open("last_cal.json", "wt") as f:
        json.dump(response.json(), f)

    return response.json()


def find_free_slots(calendar_json):
    free_slots = []
    for day in calendar_json["days"]:
        if day["status"] == "AVAILABLE":
            for zone in day["zonesSchedule"]:
                for slot in zone["slots"]:
                    if slot["status"] == "AVAILABLE":
                        free_slots.append(slot)
    return free_slots


def notify_discord(slots):
    global notif_hour, slots_notified
    discord_wh = DiscordWebhook(url=DWEBHOOK, username="Glovo")

    for slot in slots:
        embed = DiscordEmbed(
            title="Sloty", description="Są wolne sloty!!", color="FFB700"
        )
        start_dt = datetime_from_utc_to_local(
            datetime.fromtimestamp(slot["startTime"] / 1000)
        )
        end_dt = datetime_from_utc_to_local(
            datetime.fromtimestamp(slot["endTime"] / 1000)
        )
        embed.add_embed_field(name="Data", value=start_dt.strftime("%d/%m/%Y"))
        embed.add_embed_field(name="Start", value=start_dt.strftime("%H:%M"))
        embed.add_embed_field(name="Koniec", value=end_dt.strftime("%H:%M"))
        embed.add_embed_field(name="Mnożnik", value=slot["tags"]["label"])
        slots_notified.append(slot["id"])
        discord_wh.add_embed(embed)

    discord_wh.execute()


@repeat(every(INTERVAL_SECONDS).seconds)
def run():
    global notif_hour, slots_notified
    slots = find_free_slots(g_calendar())

    if notif_hour != datetime.now().hour:
        slots_notified = []
        notif_hour = datetime.now().hour

    for slot in slots[:]:  # remove already notified slots this hour
        if slot["id"] in slots_notified:
            slots.remove(slot)
            continue

        for hour_span in hours_wanted:
            start_dt = datetime.fromtimestamp(slot["startTime"] / 1000)
            end_dt = datetime.fromtimestamp(slot["endTime"] / 1000)
            if start_dt.hour >= hour_span[0] and end_dt.hour <= hour_span[1]:
                continue
            else:
                slots.remove(slot)

    if len(slots) > 0:
        notify_discord(slots)
        print(json.dumps(slots))

    sys.stdout.write("\rdzialam " + str(datetime.now()))
    sys.stdout.flush()


while True:
    run_pending()
    t = schedule.idle_seconds()
    if t is not None and t > 0:
        time.sleep(t)
