# GlovoPLZ

## O skrypcie

Napisałem takiego skrypcika bo mam 0 dostępnych slotów jak otwiera mi się kalendarz, i w sumie nie mam innej opcji niz wychwycić jakieś losowo zwalniane sloty. Skrypt sprawdza kalendarz co jakiś określony czas(30 sekund skonfigurowane w zmiennej INTERVAL_SECONDS). Jak są wolne sloty wysyła powiadomienie na discord o dostępnym slocie.
![Powiadomienie screenshot](/instalacja_skreeny/discord.jpg)
Wiem że sie da automatycznie kraść sloty ale myśle że to troche przesada.

## UWAGA

Glovo prawdopodobnie nie zbyt by sie cieszyło że takie cośik sie robi a lubią banować za byle co... to jakby jakimś cudem sie dowiedzieli że tego używasz to prawdopodobnie szybko tą sprawę załatwią. Taki tam nie rób tego bo to zło i wgl to tylko do celów edukacyjnych.

## UWAGA NR 2

Do API glovo chyba można być zalogowanym jednocześnie tylko na jednym urządzeniu, także podczas używania tego skryptu wyloguje cię z aplikacji Glovo Couriers. Można sobie sie zalogować spowrotem żeby zarezerwować slot ale po 20 minutach spowrotem cię wyrzuci. Zalecam wyłączyć skrypt jak chcemy aktywnie używać aplikacji Glovo Couriers.

## Instalacja Windows

1. Zainstaluj [Pythona - https://www.python.org/downloads/](https://www.python.org/downloads)
   Podczas instalacji zaznacz opcję aby dodać python do PATH
   ![Python installer screenshot](/instalacja_skreeny/python.png)
2. Sciągnij te repozytorium i umieść pliki w jednym folderze
3. Otwórz plik glovoplz.py w edytorze tekstowym
   ![Windows context menu open in notepad](/instalacja_skreeny/notatnik.png)
   Wypełnij swojego użytkownika, hasło, kod miasta, i [webhook url z discord](https://support.discord.com/hc/pl/articles/228383668-Wst%C4%99p-do-Webhook%C3%B3w).
   ![config screenshot](/instalacja_skreeny/konfig.png)
   Ustaw pożądane godziny o ktorych chcesz być powiadomiana/y w zmiennej hours wanted
   ![hours screenshot](/instalacja_skreeny/godziny.png)
4. Odpal run.bat. Przy pierwszym włączeniu program zainstaluje potrzebne paczki dla python. Program zaczyna działać po 30 sekundach i sygnalizuje to tekstem "dzialam DATA CZAS".
