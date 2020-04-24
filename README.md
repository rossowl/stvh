# stvh

sudo apt install ffmpeg python3 python3-requests python3-tz python3-lxml<br/>

copy sledovanitv.py and sledovanitv_settings.py to /home/hts/bin/<br/>
check if sledovanitv.py is executable<br/>

edit sledovanitv_settings.py and insert your web login and password<br/>

/home/hts/bin/sledovanitv.py register

edit sledovanitv_settings.py and insert your device id and password from registration above<br/>

create cache directory as is in the file<br/>

create playlist:<br/>
/home/hts/bin/sledovanitv.py playlist > playlist.m3u<br/>

create new automatic iptv network in tvheadend with path to generated playlist<br/>
wait for new services<br/>
import all new services to channels<br/>

xmltv:<br/>
/home/hts/bin/sledovanitv.py epg > /home/hts/.xmltv/xmltv.xml<br/>
cat /home/hts/.xmltv/xmltv.xml | nc -w 5 -U /home/hts/.hts/tvheadend/epggrab/xmltv.sock<br/>


