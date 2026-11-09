# Synth Set Manager – aplicația pentru seturile Kronos și Korg Pa

Făcută pe 9 noiembrie 2026, la cererea lui Răzvan: o singură aplicație, ușor de folosit cu NVDA, cu o secțiune pentru Kronos și una pentru seria Pa, în care muți lucruri dintr-un set în altul și faci seturi noi.

Numele vechi: Regatul Seturilor, apoi Sintetizatoare Management; din 9 noiembrie 2026 se numește Synth Set Manager (nume profesional în engleză, cerut de Răzvan; interfața rămâne în română).

## Cum pornești
Se instalează cu SynthSetManager-Setup.exe (din release-ul „latest” de pe GitHub): fără întrebări, în AppData\Local\Programs\Synth Set Manager, cu scurtătură pe desktop și în Start.
Aplicația se deschide în Chrome, ca o pagină. Tot lucrul se face pe calculator, nimic nu iese pe internet, în afară de verificarea actualizărilor.
Se închide din tabul Setări, butonul „Închide aplicația”, sau singură după 15 minute fără pagina deschisă.

## GitHub și actualizarea
Depozitul: github.com/razvan-raftul/SynthSetManager (public, ca să meargă actualizarea fără parolă). Fiecare commit pe main face, pe windows-latest, exe-ul cu PyInstaller și installer-ul cu Inno Setup, apoi le pune în release-ul „latest” împreună cu version.txt. Versiunea e 1.0.<numărul build-ului>.
La pornire aplicația citește version.txt; dacă e mai nou, descarcă installer-ul și NVDA spune doar „Se actualizează” și procentul din 10 în 10 (prin nvdaControllerClient.dll, luat de build de la nvaccess.org), apoi îl rulează cu /VERYSILENT /AUTOUPDATE; installer-ul repornește aplicația cu --actualizat, care spune „100 la sută. Actualizare terminată.”
Urcarea se face din Chrome, pe github.com/razvan-raftul/SynthSetManager/upload/main (fișierele stau toate în rădăcină, doar build.yml în .github/workflows).

## Pagina
Trei taburi: Kronos, Seria Pa, Setări (săgeți stânga/dreapta între ele, sau Alt+1, Alt+2, Alt+3).
În Kronos și în Seria Pa, de sus în jos: Setul de unde iau, Setul în care pun, Ce aduc, Banca, Caută după nume, lista cu căsuțe de bifat (lângă fiecare nume e cât ar ocupa în setul în care pun, în MB), Ce am bifat (fiecare cu costul, cu cine împarte sample-uri și totalul împreună), Unde le pun, Cum salvez, butonul „Adu ce am bifat”, apoi Rezultat.
La fiecare bifă NVDA spune costul, cu ce alte bifate împarte sample-uri și totalul.
Cât lucrează, NVDA spune procentul din 10 în 10. La final focusul sare pe titlul Rezultat.

## Kronos
Caută seturi (X.PCG cu X.KSC lângă) în Claude working\Kronos și în Desktop\KRONOS CEAMAKITO (se schimbă din Setări).
Aduce combi-uri și programe cu tot cu programele timbrelor și multisample-urile (KMP + KSF), ca kronos_transfer.py din Kronos Tools, care a mers pe Kronos.
Așezarea, după regula lui Răzvan: combi-urile și programele cerute în U-A, pe următoarea poziție liberă după ultima ocupată; programele timbrelor în U-D, apoi U-C, U-E, U-F, U-G; programele EXi în U-B. Băncile se pot schimba din pagină.
Un program identic care există deja în țintă nu se mai copiază (se folosește acela); un multisample identic (aceleași KSF-uri) la fel.
Bifa „SW1 și SW2 pe octavă” (pusă din start) face regula permanentă din 7 noiembrie: SW1 = Octave Down, SW2 = Octave Up.
Setul înrudit al lui Ramon (UUID care diferă doar la ultimul octet) e tratat singur ca setul sursă.
La final recitește setul scris și verifică pentru fiecare zonă că duce la același sample ca la sursă.
Salvare: set nou (copia întreagă a folderului setului țintă, cu alt nume de folder, fișierele își păstrează numele, de ex. set22.PCG) sau direct în setul țintă.
Nu aduce încă: drum kit-urile și wave sequence-urile cu sample-uri user (lista le arată cu „are tobe”, „are wave sequence”).

## Seria Pa (Pa3X)
Caută foldere .SET în Claude working\Korg Pa Manager.
Aduce sunete, performance-uri, style-uri (cu STS) și pad-uri, cu sunetele, pad-urile, multisample-urile și sample-urile lor (Pa Tools\pa_transfer.py).
Setul în care pun poate fi și „Un set nou gol”: setul nou are doar ce aduci (neîncercat încă pe claviatură).
Mai are: Raport (pa_analiza), Verifică (pa_verifica) și curățenie (scoate sunetele bifate și sample-urile nefolosite, pa_curatenie).
Băncile de style USER01–03 au în director codurile 0x11–0x13 (văzut în setul Mugurel); corectat în pa_lib.

## Fișiere (în rădăcina depozitului; copia e pe PC în Synth Set Manager\Cod sursa)
main.py – pornirea. server.py – serverul local (porturile 8765–8775) și tot ce cere pagina. actualizare.py – actualizarea automată.
kronos_lib.py – citirea seturilor Kronos, costurile și transferul.
pa_lib.py, pa_transfer.py, pa_analiza.py, pa_verifica.py, pa_curatenie.py – copii din Pa Tools (pa_lib cu două mici adăugiri: set gol și băncile USER de style).
pa_ops.py – listele și costurile pentru Pa.
index.html, app.js, stil.css – pagina.
installer.iss – installer-ul. .github/workflows/build.yml – compilarea.
Setările: %APPDATA%\SynthSetManager\setari.json. Erorile: %APPDATA%\SynthSetManager\erori.txt.
Folderele implicite: Documente\Claude working\Kronos și Documente\Claude working\Korg Pa Manager.

## Testat (9 nov. 2026, pe copii ale fișierelor)
Kronos: combi I-C 015 din setul lui Ramon adus în SET 22: timbrul pe U-E 053 (U-D și U-C n-au loc liber), combi-ul pe U-A 106, multisample-ul CIGUL copiat, KSC-urile corecte, verificarea trecută, SW1/SW2 = 3/4. În PCG s-au schimbat doar locurile scrise și octeții de control.
Pa: din Ceamakito PA3X 2027 un style, un performance și un sunet într-un set gol (21,6 MB) și un sunet în USER04 într-o copie; verificarea fără erori.
Încă neîncercat pe claviaturi un set făcut de aplicație.
