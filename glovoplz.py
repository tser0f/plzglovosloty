import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import functools
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
INSTALLATION_GUID = str(uuid.uuid4()).upper()
SESSION_GUID = str(uuid.uuid4()).upper()
DEVICE_ID = ""
CITY_CODE = ""
TOKEN_FILE = "token.json"
INTERVAL_SECONDS = 15
MIN_BOOKING_HOURS_AHEAD = 12
AUTO_BOOKING_ENABLED = False

notif_hour = datetime.now().hour
slots_notified = []
booking_wanted = [(13, 20)]
booking_days_off = [6, 11]
hours_wanted = [
    (11, 22)
]  # grupy od -> do, np [(10, 12), (15, 17)] to znaczy od 10:00 do 12:00 i od 15:00 do 17:00

##
###############################################################################


def datetime_from_utc_to_local(utc_datetime) -> datetime:
    now = datetime.now()
    # offset = datetime.fromtimestamp(now) - datetime.fromtimestamp(now, pytz.UTC)
    offset = now.replace(tzinfo=timezone.utc) - now.astimezone(timezone.utc)
    return utc_datetime - offset


def glovo_headers(authorization=None) -> dict:
    headers = {
        "user-agent": "Glover/16967 CFNetwork/1498.0.2 Darwin/23.5.0",
        "glovo-location-city-code": CITY_CODE,
        "glovo-client-info": "iOS-courier/2.231.0-16967-Production",
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


def g_oauth_refresh(refreshToken) -> dict:
    json_data = {
        "refreshToken": refreshToken,
    }

    response = requests.post(
        "https://api.glovoapp.com/oauth/refresh",
        headers=glovo_headers(),
        json=json_data,
    )

    return response.json()


def g_oauth_newtoken(username, password) -> dict:
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


def g_oauth_token() -> str:
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


def g_calendar() -> dict:
    response = requests.get(
        "https://api.glovoapp.com/v4/scheduling/calendar",
        headers=glovo_headers(g_oauth_token()),
    )

    # TODO: remove this
    with open("last_cal.json", "wt") as f:
        json.dump(response.json(), f)

    return response.json()


def g_reserve_slot(slot_id) -> tuple[bool, dict]:
    json_data = {"booked": True, "storeAddressId": None}

    response = requests.put(
        f"https://api.glovoapp.com/v4/scheduling/slots/{slot_id}",
        json=json_data,
        headers=glovo_headers(g_oauth_token()),
    )

    return (response.status_code == 200, response.json())


def find_free_slots(calendar_json) -> list:
    free_slots = []
    for day in calendar_json["days"]:
        if day["status"] == "AVAILABLE":
            for zone in day["zonesSchedule"]:
                for slot in zone["slots"]:
                    if slot["status"] == "AVAILABLE":
                        free_slots.append(slot)
    return free_slots


def notify_discord_reservation(slot, result, response):
    discord_wh = DiscordWebhook(url=DWEBHOOK, username="Glovo")

    embed = DiscordEmbed(title="Rezerwacja", color="FFB700")

    if result:
        embed.description = "Zarezerwowano Slot"
    else:
        embed.description = "Nie udało się zarezerwować slotu"
        embed.add_embed_field(name="Błąd", value=response["error"]["message"])

    start_dt = datetime_from_utc_to_local(
        datetime.fromtimestamp(slot["startTime"] / 1000)
    )
    end_dt = datetime_from_utc_to_local(datetime.fromtimestamp(slot["endTime"] / 1000))
    embed.add_embed_field(name="Data", value=start_dt.strftime("%d/%m/%Y"))
    embed.add_embed_field(name="Start", value=start_dt.strftime("%H:%M"))
    embed.add_embed_field(name="Koniec", value=end_dt.strftime("%H:%M"))
    embed.add_embed_field(name="Mnożnik", value=slot["tags"]["label"])

    discord_wh.add_embed(embed)
    discord_wh.execute()


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


def catch_exceptions(cancel_on_failure=False):
    def catch_exceptions_decorator(job_func):
        @functools.wraps(job_func)
        def wrapper(*args, **kwargs):
            try:
                return job_func(*args, **kwargs)
            except:
                import traceback

                print(traceback.format_exc())
                if cancel_on_failure:
                    return schedule.CancelJob

        return wrapper

    return catch_exceptions_decorator


@repeat(every(INTERVAL_SECONDS).seconds)
@catch_exceptions()
def run():
    global notif_hour, slots_notified
    slots = find_free_slots(g_calendar())

    if notif_hour != datetime.now().hour:
        slots_notified = []
        notif_hour = datetime.now().hour

    for slot in slots[:]:  # remove already notified slots this hour
        start_dt = datetime_from_utc_to_local(
            datetime.fromtimestamp(slot["startTime"] / 1000)
        )
        end_dt = datetime_from_utc_to_local(
            datetime.fromtimestamp(slot["endTime"] / 1000)
        )
        if AUTO_BOOKING_ENABLED:
            for hour_span in booking_wanted:
                if start_dt.hour >= hour_span[0] and end_dt.hour <= hour_span[1]:
                    min_autobook_dt = datetime.now() + timedelta(
                        hours=MIN_BOOKING_HOURS_AHEAD
                    )
                    if start_dt > min_autobook_dt:
                        if start_dt.day not in booking_days_off:
                            result, response = g_reserve_slot(slot["id"])
                            notify_discord_reservation(slot, result, response)

        for hour_span in hours_wanted:
            if start_dt.hour >= hour_span[0] and end_dt.hour <= hour_span[1]:
                continue
            else:
                slots.remove(slot)

        if slot["id"] in slots_notified:
            slots.remove(slot)
            continue
    if len(slots) > 0:
        notify_discord(slots)

    sys.stdout.write("\rdzialam " + str(datetime.now()))
    sys.stdout.flush()


while True:
    run_pending()
    t = schedule.idle_seconds()
    if t is not None and t > 0:
        time.sleep(t)
