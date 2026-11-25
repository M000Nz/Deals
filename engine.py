"""
Deal Scraper engine: built-in store catalog, scraping, keyword matching, alerts.
No UI code lives here (see DealScraper.pyw).
"""
from __future__ import annotations

import json
import math
import random
import re
import shlex
import smtplib
import sqlite3
import asyncio
import atexit
import importlib
import importlib.util
import subprocess
import sys
import threading
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass, field, replace
import csv
import os
import shutil
import html as _html
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ENGINE_VERSION = 99
GITHUB_REPO = "M000Nz/Deals"
GITHUB_API = "https://api.github.com"
FROZEN = bool(getattr(sys, "frozen", False))                  # True when running as the packaged Deals.exe
# Where your data lives: next to the program when run from source, in your user profile when installed as an .exe
# (the install folder isn't writable and is replaced on every update).
DATA_DIR = (Path(os.environ.get("APPDATA") or Path.home() / ".deals") / "Deals") if FROZEN else Path(__file__).resolve().parent
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
DB_PATH = DATA_DIR / "dealscraper.db"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# --------------------------------------------------------------------------- #
# Built-in catalog: 30 tech/electronics retailers per region.
# {query} is replaced with the search words. These are each site's usual search
# URL format; sites change them, so use "Test All Stores" to see which still work.
# --------------------------------------------------------------------------- #
CATALOG: dict[str, list[tuple[str, str]]] = {
    "Australia": [
        ("StaticICE (200+ AU stores)", "https://www.staticice.com.au/cgi-bin/search.cgi?q={query}&spos=3"),
        ("OzBargain (limited-time deals)", "ozb:feeds"),
        ("Amazon AU", "https://www.amazon.com.au/s?k={query}"),
        ("JB Hi-Fi", "https://www.jbhifi.com.au/search?query={query}"),
        ("Harvey Norman", "https://www.harveynorman.com.au/catalogsearch/result/?q={query}"),
        ("The Good Guys", "https://www.thegoodguys.com.au/SearchDisplay?searchTerm={query}"),
        ("Officeworks", "https://www.officeworks.com.au/shop/officeworks/search?q={query}"),
        ("Bing Lee", "https://www.binglee.com.au/search?q={query}"),
        ("Kogan", "https://www.kogan.com/au/shop/?q={query}"),
        ("Catch", "https://www.catch.com.au/search?query={query}"),
        ("Scorptec", "https://www.scorptec.com.au/search/go?w={query}"),
        ("PLE Computers", "https://www.ple.com.au/Search?q={query}"),
        ("Umart", "https://www.umart.com.au/search?q={query}"),
        ("Mwave", "https://www.mwave.com.au/searchresult?w={query}"),
        ("Centre Com", "https://www.centrecom.com.au/search?q={query}"),
        ("MSY", "https://www.msy.com.au/search?q={query}"),
        ("Computer Alliance", "https://www.computeralliance.com.au/search?q={query}"),
        ("Apple AU", "https://www.apple.com/au/search/{query}"),
        ("Dell AU", "https://www.dell.com/en-au/search/{query}"),
        ("Lenovo AU", "https://www.lenovo.com/au/en/search?text={query}"),
        ("HP AU", "https://www.hp.com/au-en/shop/sitesearch?keyword={query}"),
        ("Samsung AU", "https://www.samsung.com/au/search/?searchvalue={query}"),
        ("Big W", "https://www.bigw.com.au/search?q={query}"),
        ("Target AU", "https://www.target.com.au/search?text={query}"),
        ("Kmart", "https://www.kmart.com.au/search/?searchTerm={query}"),
        ("EB Games", "https://www.ebgames.com.au/search?q={query}"),
        ("Mighty Ape", "https://www.mightyape.com.au/search?q={query}"),
        ("VideoPro", "https://videopro.com.au/search?q={query}"),
        ("Camera House", "https://www.camerahouse.com.au/catalogsearch/result/?q={query}"),
        ("Microsoft AU", "https://www.microsoft.com/en-au/search/shop?q={query}"),
        ("Back Market AU", "https://www.backmarket.com.au/en-au/search?q={query}"),
        ("Cash Converters", "https://www.cashconverters.com.au/shop/search?q={query}"),
        ("MyDeal", "https://www.mydeal.com.au/search?q={query}"),
        ("Appliances Online", "https://www.appliancesonline.com.au/search/?q={query}"),
        ("Mobileciti", "https://www.mobileciti.com.au/search?q={query}"),
        ("Allphones", "https://www.allphones.com.au/search?q={query}"),
        ("PC Case Gear", "https://www.pccasegear.com/search?query={query}"),
        ("JW Computers", "https://www.jw.com.au/search?q={query}"),
        ("Evatech", "https://www.evatech.com.au/search?q={query}"),
        ("Shopping Express", "https://www.shoppingexpress.com.au/search?q={query}"),
        ("AusPCMarket", "https://www.auspcmarket.com.au/search?q={query}"),
        ("Harris Technology", "https://www.harristechnology.com.au/search?q={query}"),
        ("Digidirect", "https://www.digidirect.com.au/catalogsearch/result/?q={query}"),
        ("Ted's Cameras", "https://www.teds.com.au/catalogsearch/result/?q={query}"),
        ("Myer", "https://www.myer.com.au/search?query={query}"),
        ("David Jones", "https://www.davidjones.com/search?q={query}"),
        ("Bose AU", "https://www.bose.com.au/en_au/search.html?q={query}"),
        ("JBL AU", "https://www.jbl.com.au/search?q={query}"),
        ("Garmin AU", "https://www.garmin.com/en-AU/search/?query={query}"),
        ("COROS AU", "https://au.coros.com/search?q={query}"),
        ("Suunto AU", "https://www.suunto.com/en-au/search/?q={query}"),
        ("Polar AU", "https://www.polar.com/au-en/search?q={query}"),
        ("Amazfit AU", "https://au.amazfit.com/search?q={query}"),
        ("Wahoo AU", "https://au.wahoofitness.com/search?q={query}"),
        ("Strada Sports", "https://stradasports.com.au/search?q={query}"),
        ("Running Warehouse AU", "https://www.runningwarehouse.com.au/searchresults.html?search_query={query}"),
        ("Razer AU", "https://www.razer.com/au-en/search?q={query}"),
        ("PlayStation Direct", "https://direct.playstation.com/en-au/search?q={query}"),
        ("Dyson AU", "https://www.dyson.com.au/search?q={query}"),
        ("Gametraders", "https://www.gametraders.com.au/search?q={query}"),
        ("Costco AU", "https://www.costco.com.au/search?text={query}"),
        ("Bunnings", "https://www.bunnings.com.au/search/products?q={query}"),
        ("Mitre 10", "https://www.mitre10.com.au/search?q={query}"),
        ("Total Tools", "https://www.totaltools.com.au/catalogsearch/result/?q={query}"),
        ("Sydney Tools", "https://www.sydneytools.com.au/search?q={query}"),
        ("Flower Power", "https://www.flowerpower.com.au/search?q={query}"),
        ("IKEA AU", "https://www.ikea.com/au/en/search/?q={query}"),
        ("Amart Furniture", "https://www.amartfurniture.com.au/search?q={query}"),
        ("Fantastic Furniture", "https://www.fantasticfurniture.com.au/search?q={query}"),
        ("Freedom", "https://www.freedom.com.au/search?q={query}"),
        ("Temple & Webster", "https://www.templeandwebster.com.au/search?q={query}"),
        ("Adairs", "https://www.adairs.com.au/search/?q={query}"),
        ("Bed Bath N' Table", "https://www.bedbathntable.com.au/search?q={query}"),
        ("Spotlight", "https://www.spotlightstores.com/search?q={query}"),
        ("Peter's of Kensington", "https://www.petersofkensington.com.au/search?q={query}"),
        ("Kitchen Warehouse", "https://www.kitchenwarehouse.com.au/search?q={query}"),
        ("Woolworths", "https://www.woolworths.com.au/shop/search/products?searchTerm={query}"),
        ("Coles", "https://www.coles.com.au/search/products?q={query}"),
        ("Dan Murphy's", "https://www.danmurphys.com.au/search?searchTerm={query}"),
        ("Chemist Warehouse", "https://www.chemistwarehouse.com.au/search?searchtext={query}"),
        ("Priceline", "https://www.priceline.com.au/search?q={query}"),
        ("Sephora AU", "https://www.sephora.com.au/search?q={query}"),
        ("Adore Beauty", "https://www.adorebeauty.com.au/search?q={query}"),
        ("MECCA", "https://www.mecca.com/en-au/search/?q={query}"),
        ("Oz Hair & Beauty", "https://www.ozhairandbeauty.com/search?q={query}"),
        ("Healthylife", "https://www.healthylife.com.au/search?q={query}"),
        ("Rebel Sport", "https://www.rebelsport.com.au/search?q={query}"),
        ("Decathlon AU", "https://www.decathlon.com.au/search?q={query}"),
        ("Anaconda", "https://www.anacondastores.com/search?q={query}"),
        ("BCF", "https://www.bcf.com.au/search?q={query}"),
        ("Kathmandu", "https://www.kathmandu.com.au/search?q={query}"),
        ("Macpac", "https://www.macpac.com.au/search?q={query}"),
        ("Snowys", "https://www.snowys.com.au/search?q={query}"),
        ("Torpedo7 AU", "https://www.torpedo7.com.au/search?q={query}"),
        ("Nike AU", "https://www.nike.com/au/w?q={query}"),
        ("Adidas AU", "https://www.adidas.com.au/search?q={query}"),
        ("The Iconic", "https://www.theiconic.com.au/catalog/?q={query}"),
        ("Culture Kings", "https://www.culturekings.com.au/search?q={query}"),
        ("Platypus Shoes", "https://www.platypusshoes.com.au/search?q={query}"),
        ("Hype DC", "https://www.hypedc.com/search?q={query}"),
        ("Uniqlo AU", "https://www.uniqlo.com/au/en/search?q={query}"),
        ("Cotton On", "https://cottonon.com/AU/search/?q={query}"),
        ("Baby Bunting", "https://www.babybunting.com.au/search?q={query}"),
        ("Toys R Us AU", "https://www.toysrus.com.au/search?q={query}"),
        ("Toyworld", "https://www.toyworld.com.au/search?q={query}"),
        ("LEGO AU", "https://www.lego.com/en-au/search?q={query}"),
        ("Pet Circle", "https://www.petcircle.com.au/search?q={query}"),
        ("Petbarn", "https://www.petbarn.com.au/search?q={query}"),
        ("PetStock", "https://www.petstock.com.au/search?q={query}"),
        ("Supercheap Auto", "https://www.supercheapauto.com.au/search?q={query}"),
        ("Repco", "https://www.repco.com.au/en/search?q={query}"),
        ("Autobarn", "https://www.autobarn.com.au/search?q={query}"),
        ("Dymocks", "https://www.dymocks.com.au/search?q={query}"),
        ("Booktopia", "https://www.booktopia.com.au/search?keywords={query}"),
        ("Sky Music", "https://www.skymusic.com.au/search?q={query}"),
        ("Store DJ", "https://www.storedj.com.au/search?q={query}"),
        ("Getprice (price comparison)", "https://www.getprice.com.au/searchresult?q={query}"),
        ("Deals Direct", "https://www.dealsdirect.com.au/search?q={query}"),
        ("OO.com.au", "https://www.oo.com.au/search?q={query}"),
        ("Groupon AU", "https://www.groupon.com.au/browse/deals?query={query}"),
        ("ALDI AU", "https://www.aldi.com.au/results?q={query}"),
        ("Techbuy", "https://www.techbuy.com.au/search?q={query}"),
        ("Computer Lounge", "https://www.computerlounge.com.au/search?q={query}"),
        ("Austin Computers", "https://www.austin.net.au/search?q={query}"),
        ("Aftershock PC", "https://www.aftershockpc.com.au/search?q={query}"),
        ("Glink", "https://www.glink.com.au/search?q={query}"),
        ("Wireless1", "https://www.wireless1.com.au/search?q={query}"),
        ("Sony AU", "https://www.sony.com.au/search?q={query}"),
        ("LG AU", "https://www.lg.com/au/search/?q={query}"),
        ("ASUS AU Store", "https://www.asus.com/au/search/?q={query}"),
        ("Jaycar", "https://www.jaycar.com.au/search?q={query}"),
        ("Altronics", "https://www.altronics.com.au/search/?q={query}"),
        ("Core Electronics", "https://core-electronics.com.au/catalogsearch/result/?q={query}"),
        ("Little Bird", "https://littlebirdelectronics.com.au/search?q={query}"),
        ("Georges Cameras", "https://www.georgescameras.com.au/search?q={query}"),
        ("Addicted to Audio", "https://www.addictedtoaudio.com.au/search?q={query}"),
        ("Zing Pop Culture", "https://zingpopculture.com.au/search?q={query}"),
        ("The Gamesmen", "https://www.thegamesmen.com.au/search?q={query}"),
        ("Winning Appliances", "https://www.winningappliances.com.au/search?q={query}"),
        ("Betta Home Living", "https://www.betta.com.au/search?q={query}"),
        ("Appliance Central", "https://www.appliancecentral.com.au/search?q={query}"),
        ("Domayne", "https://www.domayne.com.au/search?q={query}"),
        ("Nick Scali", "https://www.nickscali.com.au/search?q={query}"),
        ("Koala", "https://au.koala.com/search?q={query}"),
        ("Brosa", "https://www.brosa.com.au/search?q={query}"),
        ("Matt Blatt", "https://www.mattblatt.com.au/search?q={query}"),
        ("Zanui", "https://www.zanui.com.au/search?q={query}"),
        ("Lounge Lovers", "https://www.loungelovers.com.au/search?q={query}"),
        ("Early Settler", "https://www.earlysettler.com.au/search?q={query}"),
        ("Toolkit Depot", "https://www.toolkitdepot.com.au/search?q={query}"),
        ("Tools Warehouse", "https://www.toolswarehouse.com.au/search?q={query}"),
        ("Surfstitch", "https://www.surfstitch.com/search?q={query}"),
        ("Foot Locker AU", "https://www.footlocker.com.au/en/search?query={query}"),
        ("Lululemon AU", "https://www.lululemon.com.au/en-au/search?q={query}"),
        ("Glue Store", "https://www.gluestore.com.au/search?q={query}"),
        ("Rip Curl AU", "https://www.ripcurl.com.au/search?q={query}"),
        ("Billabong AU", "https://www.billabong.com.au/search?q={query}"),
        ("Just Jeans", "https://www.justjeans.com.au/search?q={query}"),
        ("Jay Jays", "https://www.jayjays.com.au/search?q={query}"),
        ("Peter Alexander", "https://www.peteralexander.com.au/search?q={query}"),
        ("Country Road", "https://www.countryroad.com.au/search?q={query}"),
        ("Witchery", "https://www.witchery.com.au/search?q={query}"),
        ("Paddy Pallin", "https://www.paddypallin.com.au/search?q={query}"),
        ("Mountain Designs", "https://www.mountaindesigns.com/search?q={query}"),
        ("Wild Earth", "https://www.wildearth.com.au/search?q={query}"),
        ("Tentworld", "https://www.tentworld.com.au/search?q={query}"),
        ("Pushys", "https://www.pushys.com.au/search?q={query}"),
        ("99 Bikes", "https://www.99bikes.com.au/search?q={query}"),
        ("Reid Cycles", "https://www.reidcycles.com.au/search?q={query}"),
        ("Cell Bikes", "https://www.cellbikes.com.au/search?q={query}"),
        ("Bikebug", "https://www.bikebug.com/search?q={query}"),
        ("Bulk Nutrients", "https://www.bulknutrients.com.au/search?q={query}"),
        ("Supplement Mart", "https://www.supplementmart.com.au/search?q={query}"),
        ("Protein Supplies Australia", "https://www.proteinsuppliesaustralia.com.au/search?q={query}"),
        ("Baby Kingdom", "https://www.babykingdom.com.au/search?q={query}"),
        ("Budget Pet Products", "https://www.budgetpetproducts.com.au/search?q={query}"),
        ("Sparesbox", "https://www.sparesbox.com.au/search?q={query}"),
        ("Tyroola", "https://www.tyroola.com.au/search?q={query}"),
        ("Readings", "https://www.readings.com.au/search?q={query}"),
        ("Angus & Robertson", "https://www.angusrobertson.com.au/search?q={query}"),
        ("Better Music", "https://www.bettermusic.com.au/search?q={query}"),
        ("Billy Hyde Music", "https://www.billyhyde.com.au/search?q={query}"),
        ("Manny's Music", "https://www.mannys.com.au/search?q={query}"),
        ("BWS", "https://bws.com.au/search?searchTerm={query}"),
        ("Liquorland", "https://www.liquorland.com.au/search?q={query}"),
    ],
}
REGIONS = list(CATALOG)

# Which kinds of products each store sells. A search only visits stores that match what you typed
# (plus the general stores), which is how the list can grow without searches getting slower.
STORE_CATS = {
    "StaticICE (200+ AU stores)": "all", "OzBargain (limited-time deals)": "all",
    "Amazon AU": "general", "Kogan": "general", "Catch": "general", "MyDeal": "general", "Big W": "general",
    "Target AU": "general", "Kmart": "general", "Myer": "general", "David Jones": "general",
    "Costco AU": "general", "Back Market AU": "tech", "Cash Converters": "general",
    "JB Hi-Fi": "tech gaming home", "Harvey Norman": "tech home", "The Good Guys": "tech home",
    "Officeworks": "tech office", "Bing Lee": "tech home", "Scorptec": "tech", "PLE Computers": "tech",
    "Umart": "tech", "Mwave": "tech", "Centre Com": "tech", "MSY": "tech", "Computer Alliance": "tech",
    "Apple AU": "tech", "Dell AU": "tech", "Lenovo AU": "tech", "HP AU": "tech", "Samsung AU": "tech home",
    "EB Games": "gaming toys", "Mighty Ape": "gaming toys books", "VideoPro": "tech", "Camera House": "tech",
    "Microsoft AU": "tech gaming", "Appliances Online": "home", "Mobileciti": "tech", "Allphones": "tech",
    "PC Case Gear": "tech", "JW Computers": "tech", "Evatech": "tech", "Shopping Express": "tech home",
    "AusPCMarket": "tech", "Harris Technology": "tech", "Digidirect": "tech", "Ted's Cameras": "tech",
    "Bose AU": "tech", "JBL AU": "tech", "Garmin AU": "tech sports", "COROS AU": "tech sports", "Suunto AU": "tech sports outdoor", "Polar AU": "tech sports",
    "Amazfit AU": "tech sports", "Wahoo AU": "tech sports", "Strada Sports": "sports", "Running Warehouse AU": "sports fashion", "Razer AU": "tech gaming",
    "PlayStation Direct": "gaming", "Dyson AU": "home beauty", "Gametraders": "gaming",
    "Bunnings": "diy garden home", "Mitre 10": "diy garden", "Total Tools": "diy auto", "Sydney Tools": "diy",
    "Flower Power": "garden", "IKEA AU": "home", "Amart Furniture": "home", "Fantastic Furniture": "home",
    "Freedom": "home", "Temple & Webster": "home", "Adairs": "home", "Bed Bath N' Table": "home",
    "Spotlight": "home diy", "Peter's of Kensington": "home", "Kitchen Warehouse": "home",
    "Woolworths": "grocery", "Coles": "grocery", "Dan Murphy's": "grocery", "Chemist Warehouse": "beauty baby",
    "Priceline": "beauty", "Sephora AU": "beauty", "Adore Beauty": "beauty", "MECCA": "beauty",
    "Oz Hair & Beauty": "beauty", "Healthylife": "beauty", "Rebel Sport": "sports fashion",
    "Decathlon AU": "sports", "Anaconda": "sports outdoor", "BCF": "sports outdoor", "Kathmandu": "outdoor fashion",
    "Macpac": "outdoor fashion", "Snowys": "outdoor", "Torpedo7 AU": "sports outdoor", "Nike AU": "fashion sports",
    "Adidas AU": "fashion sports", "The Iconic": "fashion", "Culture Kings": "fashion", "Platypus Shoes": "fashion",
    "Hype DC": "fashion", "Uniqlo AU": "fashion", "Cotton On": "fashion", "Baby Bunting": "baby",
    "Toys R Us AU": "toys baby", "Toyworld": "toys", "LEGO AU": "toys", "Pet Circle": "pets", "Petbarn": "pets",
    "PetStock": "pets", "Supercheap Auto": "auto", "Repco": "auto", "Autobarn": "auto", "Dymocks": "books",
    "Booktopia": "books", "Sky Music": "music", "Store DJ": "music",
    "Getprice (price comparison)": "all", "Deals Direct": "general", "OO.com.au": "general",
    "Groupon AU": "general", "ALDI AU": "general grocery", "Techbuy": "tech",
    "Computer Lounge": "tech", "Austin Computers": "tech", "Aftershock PC": "tech gaming",
    "Glink": "tech", "Wireless1": "tech", "Sony AU": "tech gaming",
    "LG AU": "tech home", "ASUS AU Store": "tech gaming", "Jaycar": "tech diy",
    "Altronics": "tech diy", "Core Electronics": "tech diy", "Little Bird": "tech diy",
    "Georges Cameras": "tech", "Addicted to Audio": "tech", "Zing Pop Culture": "toys gaming",
    "The Gamesmen": "gaming", "Winning Appliances": "home", "Betta Home Living": "home",
    "Appliance Central": "home", "Domayne": "home", "Nick Scali": "home",
    "Koala": "home", "Brosa": "home", "Matt Blatt": "home",
    "Zanui": "home", "Lounge Lovers": "home", "Early Settler": "home",
    "Toolkit Depot": "diy", "Tools Warehouse": "diy", "Surfstitch": "fashion sports",
    "Foot Locker AU": "fashion sports", "Lululemon AU": "fashion sports", "Glue Store": "fashion",
    "Rip Curl AU": "fashion sports", "Billabong AU": "fashion sports", "Just Jeans": "fashion",
    "Jay Jays": "fashion", "Peter Alexander": "fashion", "Country Road": "fashion home",
    "Witchery": "fashion", "Paddy Pallin": "outdoor", "Mountain Designs": "outdoor fashion",
    "Wild Earth": "outdoor", "Tentworld": "outdoor", "Pushys": "sports",
    "99 Bikes": "sports", "Reid Cycles": "sports", "Cell Bikes": "sports",
    "Bikebug": "sports", "Bulk Nutrients": "sports beauty", "Supplement Mart": "sports beauty",
    "Protein Supplies Australia": "sports beauty", "Baby Kingdom": "baby", "Budget Pet Products": "pets",
    "Sparesbox": "auto", "Tyroola": "auto", "Readings": "books",
    "Angus & Robertson": "books", "Better Music": "music", "Billy Hyde Music": "music",
    "Manny's Music": "music", "BWS": "grocery", "Liquorland": "grocery",
}

CATEGORY_WORDS = {
    "tech": "wifi wireless mesh extender ethernet tplink tp archer deco eero netgear ubiquiti unifi mikrotik laptop notebook macbook ipad tablet phone iphone android smartphone galaxy pixel monitor display keyboard mouse "
            "headphones headphone earbuds airpods speaker soundbar tv television router modem ssd hdd nvme ram gpu cpu "
            "graphics motherboard processor charger cable usb hdmi camera lens drone gopro printer scanner webcam microphone "
            "smartwatch watch fitbit garmin coros suunto polar amazfit wahoo whoop oura  kindle projector nas switch vr oculus quest powerbank sony samsung lg apple bose sennheiser jbl logitech asus acer msi lenovo dell hp nvidia amd intel canon nikon panasonic philips xiaomi google huawei oppo oneplus anker ugreen tplink netgear ubiquiti seagate wd sandisk kingston corsair razer steelseries",
    "gaming": "playstation ps5 ps4 xbox switch nintendo steam game games gaming controller console zelda mario pokemon",
    "home": "fridge refrigerator freezer washer washing dryer dishwasher oven microwave cooktop rangehood vacuum robot "
            "airfryer fryer kettle toaster blender coffee espresso machine mattress sofa couch bed desk chair table lamp "
            "heater fan aircon conditioner purifier humidifier cookware pan knife towel sheets quilt pillow rug curtain "
            "shelf wardrobe bookcase dyson thermomix",
    "diy": "drill saw sander grinder impact driver tool tools toolbox ladder paint wrench spanner hammer makita dewalt milwaukee "
           "ryobi bosch stanley screws bolts timber hose generator pressure washer workbench",
    "garden": "lawn mower mowers whipper trimmer plant plants pot seeds soil fertiliser garden bbq barbecue pergola hose "
              "sprinkler hedge chainsaw blower",
    "fashion": "shoes sneakers boots jacket jeans shirt tshirt hoodie dress jumper pants shorts socks bag backpack wallet "
               "sunglasses nike adidas puma jordan asics newbalance uniqlo levis",
    "sports": "watch smartwatch coros suunto polar amazfit wahoo whoop garmin running triathlon nike adidas puma asics gym treadmill dumbbell weights kettlebell yoga bike bicycle ebike scooter golf tennis racquet cricket football "
              "soccer basketball surfboard wetsuit fishing rod reel swimming helmet protein",
    "outdoor": "tent camping sleeping swag hiking boots backpack esky cooler stove fishing kayak paddleboard 4wd",
    "baby": "pram stroller cot nappy nappies carseat capsule highchair bassinet baby toddler formula",
    "toys": "lego toy toys doll puzzle boardgame barbie nerf playmobil hotwheels kids",
    "pets": "dog cat puppy kitten pet food leash collar litter aquarium fish bird",
    "beauty": "perfume fragrance makeup skincare serum moisturiser shampoo conditioner hairdryer straightener vitamins "
              "supplement razor shaver toothbrush sunscreen lipstick foundation cologne",
    "fragrance": "perfume perfumes fragrance cologne parfum eau edp edt aftershave sauvage aventus creed lattafa armaf "
                 "tomford davidoff azzaro rabanne gaultier herrera diptyque jomalone",
    "luxury": "luxury designer gucci prada chanel dior louboutin hermes louis vuitton cartier rolex omega tiffany burberry "
              "versace fendi balenciaga givenchy ysl saint laurent bulgari tagheuer breitling longines tudor pandora "
              "swarovski coach montblanc handbag handbags jewellery jewelry necklace bracelet earrings pearl diamond",
    "auto": "tyre tyres tire car dashcam battery oil wiper seat cover roofrack jumpstarter",
    "books": "book books novel textbook cookbook biography manga",
    "grocery": "coffee tea chocolate wine beer whisky gin vodka snacks nappies milk cereal pasta",
    "office": "pen notebook stationery whiteboard shredder laminator paper ink toner",
    "music": "guitar piano keyboard drum amp amplifier synthesizer dj turntable ukulele violin",
}
WORD_CATS: dict[str, set[str]] = {}
for _c, _w in CATEGORY_WORDS.items():
    for _x in _w.split():
        WORD_CATS.setdefault(_x, set()).add(_c)


def detect_categories(keywords: str) -> set[str]:
    cats: set[str] = set()
    for t in re.findall(r"[a-z0-9]+", keywords.lower()):
        for w in (t, t.rstrip("s")):
            cats |= WORD_CATS.get(w, set())
    return cats


def select_stores(stores: list[dict], keywords: str, cfg: dict | None = None) -> list[dict]:
    """Stores worth searching for these keywords: general + price-comparison sites + the matching categories.
    If the words say nothing about the kind of product, every store is searched."""
    if (cfg or {}).get("scope", "smart") == "all":
        return stores
    cats = detect_categories(keywords)
    if not cats:
        return stores
    keep = []
    for st in stores:
        sc = set((st.get("cats") or "all").split())
        if sc & {"all", "general"} or sc & cats:
            keep.append(st)
    return keep


DEFAULTS = {"region": "Australia", "interval": "60", "currency": "$", "popups": "1", "theme": "dark",
            "auto": "0", "hide_acc": "0", "sort": "Best match", "limited": "0", "browser": "1", "blocked": "ebay", "scope": "smart",
            "health_auto": "1", "update_url": "https://raw.githubusercontent.com/M000Nz/Deals/main/Version.txt", "alert_mode": "instant", "quiet_on": "0", "quiet_start": "22", "quiet_end": "7", "summary_hour": "8", "show_codes": "1", "digest_on": "0", "digest_hour": "8"}
ALERT_MIN_SCORE = 50
SECRET_KEYS = {"discord", "tg_token", "email_pass"}


# --------------------------------------------------------------------------- #
# Database + settings
# --------------------------------------------------------------------------- #
_DB_READY: set = set()
_DB_LOCK = threading.RLock()


def db() -> sqlite3.Connection:
    """Open the database. The schema, repair and upgrade steps run once per database (and again after a
    restore or a shop-list sync), not on every call - they used to run hundreds of times a minute."""
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    key = str(DB_PATH)
    if key not in _DB_READY:
        with _DB_LOCK:
            if key not in _DB_READY:
                con.executescript(_SCHEMA)
                _repair_after_schema(con)
                _finish_db(con)
                _DB_READY.add(key)
    elif not _SEEDED:
        with _DB_LOCK:
            _finish_db(con)
    return con


_SCHEMA = (
        """
        CREATE TABLE IF NOT EXISTS watchlist(
            id INTEGER PRIMARY KEY, keywords TEXT NOT NULL,
            max_price REAL, min_drop_pct REAL DEFAULT 10,
            best_price REAL, best_store TEXT, best_title TEXT, best_url TEXT, checked_at REAL);
        CREATE TABLE IF NOT EXISTS stores(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL,
            search_url TEXT NOT NULL, item TEXT, title TEXT, price TEXT, was_price TEXT, link TEXT,
            enabled INTEGER DEFAULT 1, status TEXT DEFAULT 'Not tested', tested_at REAL,
            custom INTEGER DEFAULT 0, UNIQUE(name, region));
        CREATE TABLE IF NOT EXISTS prices(
            id INTEGER PRIMARY KEY, item_id INTEGER, store TEXT, url TEXT,
            title TEXT, price REAL, seen_at REAL);
        CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY, item_id INTEGER, keywords TEXT, title TEXT, store TEXT,
            url TEXT, price REAL, reasons TEXT, sent_at REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS picks(
            id INTEGER PRIMARY KEY, kind TEXT NOT NULL, url TEXT NOT NULL, store TEXT, title TEXT,
            price REAL, was REAL, pct REAL, image TEXT, source TEXT, expires REAL, votes INTEGER DEFAULT 0,
            terms TEXT, found_at REAL, basis TEXT DEFAULT 'was', UNIQUE(kind, url));
        CREATE TABLE IF NOT EXISTS reviews(
            key TEXT PRIMARY KEY, rating REAL, count INTEGER DEFAULT 0, label TEXT, n INTEGER DEFAULT 0, at REAL);
        CREATE TABLE IF NOT EXISTS saved_searches(
            id INTEGER PRIMARY KEY, query TEXT NOT NULL, max_price REAL, min_rating REAL,
            deals_only INTEGER DEFAULT 1, created REAL);
        CREATE TABLE IF NOT EXISTS vocab(word TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS seen(url TEXT NOT NULL, price REAL NOT NULL, at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS seen_url ON seen(url, at);
        CREATE TABLE IF NOT EXISTS hidden_urls(
            url TEXT PRIMARY KEY, store TEXT, title TEXT, price REAL, correct REAL, at REAL);
        CREATE TABLE IF NOT EXISTS feedback(
            url TEXT PRIMARY KEY, verdict TEXT NOT NULL, terms TEXT, title TEXT, at REAL);
        CREATE TABLE IF NOT EXISTS foryou_seen(url TEXT PRIMARY KEY, at REAL);
        """
)


def _repair_after_schema(con):
    """Databases from much older versions can have tables with missing columns (CREATE IF NOT EXISTS leaves them alone).
    Add what's missing; a stores table too old to use is set aside and rebuilt (the built-in stores are re-added)."""
    ref = sqlite3.connect(":memory:")
    ref.executescript(_SCHEMA)
    ref.execute("CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL, "
                "search_url TEXT NOT NULL, item TEXT, title TEXT, price TEXT, was_price TEXT, link TEXT, "
                "enabled INTEGER DEFAULT 1, status TEXT DEFAULT 'Not tested', tested_at REAL, custom INTEGER DEFAULT 0, "
                "UNIQUE(name, region))")
    changed = False
    for (tname,) in ref.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({tname})")}
        want = ref.execute(f"PRAGMA table_info({tname})").fetchall()
        missing = [r for r in want if r[1] not in have]
        if not missing:
            continue
        if not changed:
            changed = True
            try:                                                   # keep a copy of the untouched file, just in case
                import shutil
                shutil.copy2(DB_PATH, str(DB_PATH) + ".before-repair")
            except OSError:
                pass
        if tname == "stores" and any(r[1] in ("name", "region", "search_url") for r in missing):
            con.execute(f"ALTER TABLE stores RENAME TO stores_old_{int(time.time())}")
            con.executescript(_SCHEMA)
            con.execute("CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL, "
                        "search_url TEXT NOT NULL, item TEXT, title TEXT, price TEXT, was_price TEXT, link TEXT, "
                        "enabled INTEGER DEFAULT 1, status TEXT DEFAULT 'Not tested', tested_at REAL, custom INTEGER DEFAULT 0, "
                        "UNIQUE(name, region))")
            continue
        for _cid, col, typ, _nn, dflt, _pk in missing:
            ddl = f"ALTER TABLE {tname} ADD COLUMN {col} {typ or ''}" + (f" DEFAULT {dflt}" if dflt is not None else "")
            try:
                con.execute(ddl)
            except sqlite3.OperationalError:
                pass
    con.commit()
    ref.close()


def _finish_db(con):
    wcols = [r[1] for r in con.execute("PRAGMA table_info(watchlist)")]
    for col, ddl in (("paused", "INTEGER DEFAULT 0"), ("ignore_stores", "TEXT DEFAULT ''"),
                     ("want_stock", "INTEGER DEFAULT 0"), ("had_stock", "INTEGER DEFAULT 1"),
                     ("folder", "TEXT DEFAULT ''"), ("stock_store", "TEXT DEFAULT ''")):
        if col not in wcols:
            con.execute(f"ALTER TABLE watchlist ADD COLUMN {col} {ddl}")
            con.commit()
    pcols = [r[1] for r in con.execute("PRAGMA table_info(picks)")]
    if "basis" not in pcols:
        con.execute("ALTER TABLE picks ADD COLUMN basis TEXT DEFAULT 'was'")
        con.commit()
    prcols = [r[1] for r in con.execute("PRAGMA table_info(prices)")]
    if "reg" not in prcols:
        con.execute("ALTER TABLE prices ADD COLUMN reg REAL")
        con.commit()
    acols = [r[1] for r in con.execute("PRAGMA table_info(alerts)")]
    if "notified" not in acols:
        con.execute("ALTER TABLE alerts ADD COLUMN notified INTEGER DEFAULT 1")
        con.commit()
    cols = [r[1] for r in con.execute("PRAGMA table_info(stores)")]
    for col, ddl in (("item", "TEXT"), ("title", "TEXT"), ("price", "TEXT"), ("was_price", "TEXT"), ("link", "TEXT"),
                     ("enabled", "INTEGER DEFAULT 1"), ("status", "TEXT DEFAULT 'Not tested'"), ("tested_at", "REAL"),
                     ("custom", "INTEGER DEFAULT 0"), ("alt_url", "TEXT DEFAULT ''"),   # alt_url = a repaired search address
                     ("use_browser", "INTEGER DEFAULT 0"), ("fail_streak", "INTEGER DEFAULT 0"),
                     ("skip_until", "REAL DEFAULT 0"), ("cats", "TEXT DEFAULT 'all'")):
        if col not in cols:
            con.execute(f"ALTER TABLE stores ADD COLUMN {col} {ddl}")
            con.commit()
    global _SEEDED
    if not _SEEDED:
        seed_catalog(con)
        con.execute("DELETE FROM seen WHERE at < ?", (time.time() - 400 * 86400,))
        con.commit()
        migrate_secrets(con)
        try:
            os.chmod(DB_PATH, 0o600)               # your database holds alert settings: keep it private (Mac/Linux)
        except OSError:
            pass
        _SEEDED = True
    return con


_SEEDED = False


REMOTE_CATALOG_URL = "https://raw.githubusercontent.com/M000Nz/Deals/main/stores.json"
_CAT_WORD = re.compile(r"^[a-z]{2,12}$")
_REMOTE_CACHE: dict = {}


def remote_cache_path() -> Path:
    return DB_PATH.parent / "stores_remote.json"


def validate_remote_catalog(data) -> dict | None:
    """Check a downloaded shop list. Bad entries are skipped; a file that is not a shop list at all gives None.
    It is data only: names, https search addresses with {query}, product kinds and a few flags."""
    from urllib.parse import urlparse
    if not isinstance(data, dict):
        return None
    try:
        ver = int(data.get("version"))
    except (TypeError, ValueError):
        return None
    raw = data.get("stores")
    if not isinstance(raw, list) or len(raw) > 600:
        return None
    out, seen = [], set()
    for e in raw:
        if not isinstance(e, dict):
            continue
        name, url = str(e.get("name", "")).strip(), str(e.get("url", "")).strip()
        if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name) or name in seen:
            continue
        if not url.startswith("https://") or "{query}" not in url or len(url) > 300 or re.search(r"\s", url):
            continue
        host = (urlparse(url.replace("{query}", "x")).hostname or "").lower()
        if "." not in host or host == "localhost" or re.fullmatch(r"[\d.:]+", host):
            continue
        cats = e.get("cats")
        if isinstance(cats, str):
            cats = cats.split()
        cats = [c for c in cats if isinstance(c, str) and _CAT_WORD.match(c)] if isinstance(cats, list) else []
        seen.add(name)
        out.append({"name": name, "url": url, "cats": " ".join(cats) or "all", "browser": e.get("browser") is True,
                    "enabled": e.get("enabled") is not False, "note": str(e.get("note", ""))[:140]})
    return {"version": ver, "stores": out}


def load_remote_catalog() -> dict | None:
    """The last shared shop list that was downloaded (kept on this PC so it works offline)."""
    p = remote_cache_path()
    try:
        mt = p.stat().st_mtime
    except OSError:
        return None
    if _REMOTE_CACHE.get("key") == (str(p), mt):
        return _REMOTE_CACHE.get("data")
    try:
        data = validate_remote_catalog(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        data = None
    _REMOTE_CACHE.update(key=(str(p), mt), data=data)
    return data


def sync_remote_catalog(settings: dict | None = None, force: bool = False) -> tuple[bool, str]:
    """Download the shared shop list from GitHub and apply it. Returns (changed, message)."""
    url = (settings or {}).get("catalog_url") or REMOTE_CATALOG_URL
    try:
        r = requests.get(url, timeout=(5, 10), headers={"User-Agent": "Deals-updater"})
        r.raise_for_status()
        if len(r.content) > 600_000:
            return False, "the shared shop list was too large, so it was ignored"
        data = validate_remote_catalog(r.json())
    except (requests.RequestException, ValueError):
        return False, "couldn't reach the shared shop list"
    if not data or not data["stores"]:
        return False, "the shared shop list wasn't valid, so it was ignored"
    old = load_remote_catalog()
    if old and data["version"] <= old["version"] and not force:
        return False, "the shop list is already up to date"
    before = {e["name"]: (e["url"], e["enabled"], e["cats"], e["browser"]) for e in (old or {}).get("stores", [])}
    changes = sum(1 for e in data["stores"] if before.get(e["name"]) != (e["url"], e["enabled"], e["cats"], e["browser"]))
    p = remote_cache_path()
    try:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        return False, "couldn't save the shared shop list"
    _REMOTE_CACHE.clear()
    global _SEEDED
    _SEEDED = False
    db().close()                                           # opening the database applies the new list
    if not changes:
        return False, "the shop list is already up to date"
    return True, f"shop list updated to version {data['version']} ({changes} change{'' if changes == 1 else 's'})"


def seed_catalog(con):
    """Add any new built-in stores and refresh built-in search URLs (keeps your on/off choices). The shared shop list
    downloaded from GitHub (if any) adds shops and overrides built-in addresses, categories and browser settings."""
    remote = load_remote_catalog()
    entries: dict[tuple[str, str], tuple[str, str]] = {}
    for region, stores in CATALOG.items():
        for name, url in stores:
            entries[(region, name)] = (url, STORE_CATS.get(name, "all"))
    flags: list[dict] = []
    if remote:
        for e in remote["stores"]:
            entries[("Australia", e["name"])] = (e["url"], e["cats"])
            flags.append(e)
    names = sorted({n for _, n in entries})
    con.execute("DELETE FROM stores WHERE custom=0 AND (region NOT IN (%s) OR name NOT IN (%s))"
                % (",".join("?" * len(CATALOG)), ",".join("?" * len(names))), (*CATALOG, *names))
    for (region, name), (url, cats) in entries.items():
        con.execute("INSERT OR IGNORE INTO stores(name,region,search_url,custom) VALUES(?,?,?,0)", (name, region, url))
        con.execute("UPDATE stores SET alt_url='' WHERE name=? AND region=? AND custom=0 AND search_url<>?",
                    (name, region, url))
        con.execute("UPDATE stores SET search_url=?, cats=? WHERE name=? AND region=? AND custom=0",
                    (url, cats, name, region))
    if flags:
        row = con.execute("SELECT value FROM settings WHERE key='remote_off'").fetchone()
        try:
            off = json.loads(row["value"]) if row else {}
        except ValueError:
            off = {}
        was = dict(off)
        for e in flags:
            if e["browser"]:
                con.execute("UPDATE stores SET use_browser=1 WHERE name=? AND custom=0", (e["name"],))
            if not e["enabled"]:
                if off.get(e["name"]) != remote["version"]:       # switch off once per list version, so you can switch it back on
                    note = ("Paused by the shared shop list" + (f": {e['note']}" if e["note"] else ""))[:160]
                    con.execute("UPDATE stores SET enabled=0, status=? WHERE name=? AND custom=0", (note, e["name"]))
                    off[e["name"]] = remote["version"]
            elif e["name"] in off:                                 # the list has switched it back on
                con.execute("UPDATE stores SET enabled=1, status='Not tested' WHERE name=? AND custom=0", (e["name"],))
                del off[e["name"]]
        if off != was:
            con.execute("INSERT OR REPLACE INTO settings VALUES('remote_off',?)", (json.dumps(off),))
    con.execute("INSERT OR REPLACE INTO settings VALUES('region','Australia')")   # Australia only
    con.commit()


def reset_catalog(con):
    con.execute("DELETE FROM stores WHERE custom=0")
    seed_catalog(con)


def _keyring():
    try:
        import keyring  # type: ignore
        keyring.get_keyring()
        if "fail" in type(keyring.get_keyring()).__module__.lower():
            return None
        return keyring
    except Exception:  # noqa: BLE001
        return None


def secure_store_available() -> bool:
    return _keyring() is not None


def get_settings(con) -> dict:
    s = dict(DEFAULTS)
    s.update({r["key"]: r["value"] for r in con.execute("SELECT * FROM settings")})
    for k in SECRET_KEYS:
        if str(s.get(k, "")).startswith("keyring:"):
            kr = _keyring()
            try:
                s[k] = (kr.get_password("Deals", k) or "") if kr else ""
            except Exception:  # noqa: BLE001
                s[k] = ""
    return s


def migrate_secrets(con):
    """Move any saved passwords/tokens into the system password store when one is available."""
    kr = _keyring()
    if not kr:
        return
    for r in con.execute("SELECT key, value FROM settings").fetchall():
        if r["key"] in SECRET_KEYS and r["value"] and not r["value"].startswith("keyring:"):
            try:
                kr.set_password("Deals", r["key"], r["value"])
                con.execute("UPDATE settings SET value='keyring:1' WHERE key=?", (r["key"],))
            except Exception:  # noqa: BLE001
                pass
    con.commit()


def set_setting(con, key: str, value: str):
    if key in SECRET_KEYS and value and not value.startswith("keyring:"):
        kr = _keyring()
        if kr:
            try:
                kr.set_password("Deals", key, value)
                value = "keyring:1"
            except Exception:  # noqa: BLE001
                pass
    if value == "":
        con.execute("DELETE FROM settings WHERE key=?", (key,))
    else:
        con.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, value))
    con.commit()


def active_stores(con, region: str) -> list[dict]:
    rows = con.execute("SELECT * FROM stores WHERE enabled=1 AND (region=? OR custom=1) ORDER BY name",
                       (region,)).fetchall()
    return [dict(r) for r in rows]


def money(sym: str, v: float) -> str:
    return f"{sym}{v:,.2f}"


# --------------------------------------------------------------------------- #
# Keywords + matching
# --------------------------------------------------------------------------- #
def parse_keywords(text: str) -> tuple[list[str], list[str]]:
    """'sony wh-1000xm5 "noise cancelling" -case' -> (include terms, exclude terms)"""
    try:
        toks = shlex.split(text)
    except ValueError:
        toks = text.split()
    inc, exc = [], []
    for tok in toks:
        if tok.startswith("-") and len(tok) > 1:
            exc.append(tok[1:])
        else:
            inc.append(tok)
    return inc, exc


def norm(s: str) -> str:
    """Lowercase and strip punctuation/spaces so 'WH-1000XM5' matches 'wh1000xm5'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def matches(keywords: str, title: str) -> bool:
    inc, exc = parse_keywords(keywords)
    t = norm(title)
    return bool(inc) and all(norm(w) in t for w in inc) and not any(norm(w) in t for w in exc)


def search_query(keywords: str) -> str:
    return " ".join(parse_keywords(keywords)[0])


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #
@dataclass
class Offer:
    store: str
    title: str
    price: float
    url: str
    was_price: float | None = None
    image: str | None = None
    score: float = 0.0
    accessory: bool = False
    expires: float | None = None      # limited-time deals (OzBargain): unix time the deal ends
    votes: int = 0                    # OzBargain net votes
    source: str = "store"             # store | ozb | staticice
    ref_price: float | None = None    # typical price at other shops (used to show an OzBargain discount)
    oos: bool = False                 # shown as out of stock / unavailable
    used: bool = False                # refurbished, ex-demo, open box, grey import...
    others: list = field(default_factory=list)   # the same product at other stores (set by group_offers)
    coupon: str = ""                  # a real discount code stated in an OzBargain post (never gift-card or cashback offers)
    match: str = ""                   # pasted-link searches: "exact" (same barcode / model code), "different" or "" (unknown)


class FetchError(Exception):
    def __init__(self, kind: str, msg: str):
        super().__init__(msg)
        self.kind = kind  # 'blocked' | 'notfound' | 'error'


def parse_price(text: str | None) -> float | None:
    """'$1,299.00' -> 1299.0, '1.299,00 €' -> 1299.0, '1 299' -> 1299.0"""
    if not text:
        return None
    m = re.search(r"\d[\d.,\s]*", text)
    if not m:
        return None
    s = m.group().strip().replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    try:
        return float(s.rstrip("."))
    except ValueError:
        return None


UA_ALT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          "Version/17.5 Safari/605.1.15")
OZB_UA = "DealScraper/1.0 (personal price tracker; reads public RSS feeds)"
BOT_MARKERS = ("captcha", "access denied", "just a moment", "cf-chl", "px-captcha", "pardon our interruption",
               "are you a robot", "unusual traffic", "verify you are human", "attention required")
JS_MARKERS = ('id="__next"', 'id="root"', 'id="app"', "data-reactroot", "__nuxt", "<app-root", "ng-version",
              "enable javascript", "requires javascript", "you need to enable javascript")
_SESSION = requests.Session()


def fetch(url: str, timeout=(5, 8), accept: str = "text/html,application/xhtml+xml,*/*;q=0.8",
          ua: str | None = None) -> str:
    """GET a page. A 403 gets one retry under a different browser identity before we call it blocked.
    A site that times out is given up on straight away (it won't be faster a second later)."""
    last = None
    for attempt, agent in enumerate((ua or UA, UA_ALT)):
        try:
            r = _SESSION.get(url, headers={"User-Agent": agent, "Accept": accept,
                                           "Accept-Language": "en-AU,en;q=0.9"}, timeout=timeout)
            if r.status_code == 403 and attempt == 0:
                continue
            if r.status_code in (401, 403, 429, 503):
                raise FetchError("blocked", f"HTTP {r.status_code}")
            if r.status_code == 404:
                raise FetchError("notfound", "HTTP 404")
            r.raise_for_status()
            return r.text
        except FetchError:
            raise
        except requests.Timeout:
            raise FetchError("error", "timed out")
        except requests.RequestException as e:      # connection hiccup: one more try
            last = e
    raise FetchError("error", str(last)[:80])


TRACKERS = ("google-analytics", "googletagmanager", "doubleclick", "googlesyndication", "facebook.net",
            "facebook.com/tr", "hotjar", "clarity.ms", "segment.io", "segment.com", "newrelic", "nr-data",
            "tiktok", "pinterest", "criteo", "taboola", "outbrain", "optimizely", "intercom", "zendesk",
            "livechat", "tawk.to", "bing.com/bat", "snapchat", "klaviyo", "yotpo", "trustpilot",
            "gorgias", "tidio", "crisp.chat", "drift.com", "zdassets", "freshchat", "smooch", "olark",
            "fullstory", "mouseflow", "mixpanel", "amplitude", "adsrvr", "adnxs", "googleadservices", "bugsnag", "sentry.io")


def browser_state_path() -> Path:
    return DB_PATH.parent / "browser_state.json"


class BrowserEngine:
    """One shared headless browser (Microsoft Edge / Chrome if installed, else Playwright's Chromium).
    Pages load with JavaScript like a normal visit, up to 3 at once, from any thread."""

    def __init__(self):
        self.loop = self.thread = self.browser = self.pw = self.sem = None
        self.state, self.error, self.channel, self.ua = "idle", "", "", None
        self.lock, self.ready = threading.Lock(), threading.Event()
        self.busy, self.last = 0, time.time()            # in-use count and last use, for closing it when idle
        threading.Thread(target=self._idle_watch, daemon=True).start()

    def _idle_watch(self):
        """The hidden browser (Edge/Chrome plus helper processes) uses a lot of memory. Close it after 4 quiet
        minutes; it starts again by itself, in a couple of seconds, on the next search that needs it."""
        while True:
            time.sleep(30)
            try:
                if self.state == "ready" and self.busy == 0 and time.time() - self.last > 240:
                    self.reset()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def installed() -> bool:
        return importlib.util.find_spec("playwright") is not None

    async def _shutdown(self):
        for closer in (self.browser and self.browser.close, self.pw and self.pw.stop):
            try:
                if closer:
                    await closer()
            except Exception:  # noqa: BLE001
                pass

    def reset(self):
        """Close the browser cleanly (so no stray process is left behind) and allow a fresh start."""
        loop, thread = self.loop, self.thread
        if loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), loop).result(8)
            except Exception:  # noqa: BLE001
                pass
            loop.call_soon_threadsafe(loop.stop)
            if thread:
                thread.join(5)
        self.browser = self.pw = self.loop = self.thread = None
        self.state, self.error = "idle", ""
        self.ready.clear()

    def start(self, wait: bool = True) -> bool:
        if not self.installed():
            self.state, self.error = "error", "browser add-on (playwright) is not installed"
            return False
        with self.lock:
            if self.state == "idle":
                self.state = "starting"
                self.ready.clear()
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
        if wait:
            self.ready.wait(90)
        return self.state == "ready"

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        loop.run_until_complete(self._init())
        self.ready.set()
        if self.state == "ready":
            loop.run_forever()
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _init(self):
        try:
            from playwright.async_api import async_playwright
            self.pw = await async_playwright().start()
            last = None
            for channel in ("msedge", "chrome", None):
                try:
                    kw = {"headless": True, "args": ["--disable-blink-features=AutomationControlled",
                                                     "--disable-dev-shm-usage", "--disable-gpu", "--disable-extensions",
                                                     "--disable-background-networking", "--mute-audio",
                                                     "--disable-sync", "--no-first-run",
                                                     "--blink-settings=imagesEnabled=false", "--renderer-process-limit=2",
                                                     "--disable-software-rasterizer",
                                                     "--disable-features=Translate,MediaRouter,OptimizationHints"]}
                    if channel:
                        kw["channel"] = channel
                    self.browser = await self.pw.chromium.launch(**kw)
                    self.channel = channel or "chromium"
                    break
                except Exception as e:  # noqa: BLE001
                    last = e
            if not self.browser:
                raise last or RuntimeError("no browser could be started")
            self.ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                       f"Chrome/{self.browser.version} Safari/537.36")
            self.sem = asyncio.Semaphore(3)
            self.state = "ready"
        except Exception as e:  # noqa: BLE001
            self.state = "error"
            msg = str(e).strip().splitlines()
            self.error = ("no browser found - install one from Settings" if "xecutable" in str(e)
                          else (msg[0][:160] if msg else "browser failed to start"))

    def _state(self):
        """Cookies saved after you passed a shop's check yourself (Sources > Verify), if any."""
        try:
            p = browser_state_path()
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except (OSError, ValueError):
            return None

    async def _verify(self, url: str, wait_s: int = 600) -> bool:
        """Open a real, visible browser on the shop so a person can pass its check. Cookies are kept and reused by the
        hidden browser. Returns True once the window was closed."""
        # Like a normal browser window: pop-ups stay blocked (Playwright switches that off by default, which lets chat
        # widgets and ad scripts keep opening and closing tabs).
        kw = {"headless": False, "args": ["--no-first-run"], "ignore_default_args": ["--disable-popup-blocking"]}
        if self.channel and self.channel != "chromium":
            kw["channel"] = self.channel
        browser = await self.pw.chromium.launch(**kw)
        try:
            ctx = await browser.new_context(user_agent=self.ua, locale="en-AU", timezone_id="Australia/Sydney",
                                            storage_state=self._state(), no_viewport=True)
            async def gate(route):                           # no chat widgets / trackers while you pass the check
                if any(t in route.request.url for t in TRACKERS):
                    await route.abort()
                else:
                    await route.continue_()
            await ctx.route("**/*", gate)
            page = await ctx.new_page()

            async def tidy(p):                               # a stray extra tab from a widget: close it, keep the shop
                try:
                    if p is not page and any(t in (p.url or "") for t in TRACKERS):
                        await p.close()
                except Exception:  # noqa: BLE001
                    pass
            ctx.on("page", lambda p: asyncio.ensure_future(tidy(p)))
            closed = asyncio.Event()
            browser.on("disconnected", lambda *_: closed.set())
            ctx.on("close", lambda *_: closed.set())
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:  # noqa: BLE001
                pass
            prev = self._state() or {}
            cookies, waited = None, 0
            while not closed.is_set() and waited < wait_s:
                try:
                    await asyncio.wait_for(closed.wait(), 2)
                except asyncio.TimeoutError:
                    waited += 2
                    try:
                        # cookies only: ctx.storage_state() also reads every site's local storage by opening hidden tabs
                        # on each tracker's domain, which showed up as tabs flickering open and shut
                        cookies = await ctx.cookies()
                    except Exception:  # noqa: BLE001
                        pass
            if cookies:
                p = browser_state_path()
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps({"cookies": cookies, "origins": prev.get("origins", [])}), encoding="utf-8")
                os.replace(tmp, p)
            return True
        finally:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass

    def verify(self, url: str) -> bool:
        self.busy += 1
        try:
            if not self.start():
                raise FetchError("nobrowser", self.error or "browser unavailable")
            return asyncio.run_coroutine_threadsafe(self._verify(url), self.loop).result(660)
        finally:
            self.busy -= 1
            self.last = time.time()

    _STEALTH = """
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        Object.defineProperty(navigator,'languages',{get:()=>['en-AU','en-GB','en']});
        Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
        window.chrome = window.chrome || {runtime: {}, app: {isInstalled: false}};
        const _q = navigator.permissions && navigator.permissions.query;
        if (_q) navigator.permissions.query = (p) => p && p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission}) : _q.call(navigator.permissions, p);
    """

    async def _render(self, url: str, timeout: int, warm: bool = False) -> str:
        async with self.sem:
            ctx = await self.browser.new_context(user_agent=self.ua, locale="en-AU", timezone_id="Australia/Sydney",
                                                 viewport={"width": 1024, "height": 768}, storage_state=self._state())
            try:
                await ctx.add_init_script(self._STEALTH)
                page = await ctx.new_page()

                async def gate(route):                       # skip pictures, fonts and trackers: faster, same prices
                    req = route.request
                    skip = ("image", "media", "texttrack", "eventsource", "websocket", "manifest") if warm else (
                        "image", "media", "font", "stylesheet", "texttrack", "eventsource", "websocket", "manifest")
                    if req.resource_type in skip or any(t in req.url for t in TRACKERS):
                        await route.abort()
                    else:
                        await route.continue_()

                await page.route("**/*", gate)
                if warm:                                     # bot checks often let you through once you've visited the front page
                    pu = urlparse(url)
                    try:
                        await page.goto(f"{pu.scheme}://{pu.netloc}/", wait_until="domcontentloaded", timeout=timeout * 1000)
                        await page.mouse.move(220, 260)
                        await page.wait_for_timeout(1800)
                        await page.mouse.move(500, 400)
                    except Exception:  # noqa: BLE001
                        pass
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                if warm:
                    await page.wait_for_timeout(1500)
                try:
                    await page.wait_for_function(r"document.body && /\$\s?\d/.test(document.body.innerText)",
                                                 timeout=6000)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await page.wait_for_load_state("networkidle", timeout=1500)
                except Exception:  # noqa: BLE001
                    pass
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(300)
                return await page.content()
            finally:
                await ctx.close()

    def render(self, url: str, timeout: int = 20, warm: bool = False) -> str:
        self.busy += 1
        try:
            if not self.start():
                raise FetchError("nobrowser", self.error or "browser unavailable")
            fut = asyncio.run_coroutine_threadsafe(self._render(url, timeout, warm), self.loop)
            try:
                return fut.result(timeout + 20 + (10 if warm else 0))
            except Exception as e:  # noqa: BLE001
                fut.cancel()                                  # don't leave the page open after we've given up on it
                msg = str(e).strip().splitlines()
                raise FetchError("error", (msg[0] if msg else "page failed to load")[:80])
        finally:
            self.busy -= 1
            self.last = time.time()


BROWSER = BrowserEngine()
atexit.register(lambda: BROWSER.reset() if BROWSER.state == "ready" else None)


def browser_wanted(cfg: dict | None) -> bool:
    return (cfg or {}).get("browser", "1") == "1" and BrowserEngine.installed()


def browser_status(cfg: dict | None = None) -> str:
    """Short text for the UI."""
    if (cfg or {}).get("browser", "1") != "1":
        return "off"
    if not BrowserEngine.installed():
        return "not installed"
    return {"ready": "ready", "starting": "starting...", "error": "problem: " + BROWSER.error}.get(BROWSER.state, "ready when needed")


def install_browser(log=print) -> tuple[bool, str]:
    """pip-install Playwright, then use Edge/Chrome if present or download Chromium (~150 MB)."""
    flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

    def run(args, cmd=None):
        p = subprocess.Popen(cmd or [sys.executable, "-m", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, **flags)
        for line in p.stdout:
            if line.strip():
                log(line.strip()[:110])
        return p.wait() == 0

    def playwright_install():
        """`playwright install chromium`. In the packaged app Python isn't available, so use the bundled driver."""
        if FROZEN:
            try:
                from playwright._impl._driver import compute_driver_executable, get_driver_env
                found = compute_driver_executable()
                cmd = (list(found) if isinstance(found, (tuple, list)) else [str(found)]) + ["install", "chromium"]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     env={**os.environ, **get_driver_env()}, **flags)
                for line in p.stdout:
                    if line.strip():
                        log(line.strip()[:110])
                return p.wait() == 0
            except Exception as e:  # noqa: BLE001
                log(f"browser download failed: {e}")
                return False
        return run(["playwright", "install", "chromium"])

    if not BrowserEngine.installed() and not FROZEN:
        log("Installing the browser add-on...")
        if not (run(["pip", "install", "playwright"]) or run(["pip", "install", "--user", "playwright"])):
            return False, "pip couldn't install the browser add-on"
        importlib.invalidate_caches()
    BROWSER.reset()
    if BROWSER.start():
        return True, f"ready (using {BROWSER.channel})"
    log("No Edge/Chrome found - downloading a browser (about 150 MB)...")
    if not playwright_install():
        return False, "the browser download failed"
    BROWSER.reset()
    return (True, f"ready (using {BROWSER.channel})") if BROWSER.start() else (False, BROWSER.error)


_FEED_CACHE: dict = {}
_FEED_LOCK = threading.Lock()


def fetch_cached(url: str, ttl: int = 600, **kw) -> str:
    """fetch() with a short in-memory cache (also for failures) so feeds aren't hammered."""
    now = time.time()
    with _FEED_LOCK:
        hit = _FEED_CACHE.get(url)
        if hit and now - hit[0] < ttl:
            if isinstance(hit[1], FetchError):
                raise hit[1]
            return hit[1]
    try:
        text = fetch(url, **kw)
    except FetchError as e:
        with _FEED_LOCK:
            _FEED_CACHE[url] = (now, e)
        raise
    with _FEED_LOCK:
        _FEED_CACHE[url] = (now, text)
        if len(_FEED_CACHE) > 40:                        # feeds are big strings: drop the stale ones
            for k in [k for k, v in _FEED_CACHE.items() if now - v[0] >= ttl]:
                del _FEED_CACHE[k]
    return text


def _looks_js(page: str) -> bool:
    """A page with lots of scripts and almost no visible text is built in the browser."""
    if any(m in page.lower() for m in JS_MARKERS):
        return True
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    return page.lower().count("<script") >= 5 and len(text) < 4000


def _classify_empty(page: str) -> str | None:
    """Why did a 200 page contain no products? Bot-check page, or built with JavaScript?"""
    low = page.lower()
    if any(m in low for m in BOT_MARKERS):
        return "botcheck"
    if any(m in low for m in JS_MARKERS):
        return "needsjs"
    return None


PRICE_RE = re.compile(r"(?:A\$|AU\$|US\$|\$|£|€)\s?\d[\d,]*(?:\.\d{1,2})?")
NOISE_RE = re.compile(r"(?i)(?:save|saving|you save|off|was|rrp|from)?\s*(?:\d+\s*(?:x|payments?|instal+ments?)\s*(?:of)?\s*)"
                      r"(?:A\$|AU\$|US\$|\$|£|€)\s?\d[\d,]*(?:\.\d{1,2})?(?:\s*/\s*(?:mo|month|wk|week|fortnight))?")
SAVE_RE = re.compile(r"(?i)(?:save|saving|you save)\s*(?:up to)?\s*(?:A\$|AU\$|US\$|\$|£|€)\s?\d[\d,]*(?:\.\d{1,2})?")


_CUR = r"(?:A\$|AU\$|US\$|\$|£|€)\s?\d[\d,]*(?:\.\d{1,2})?"
# "$50 off", "save $50", "extra $20 off", "take $30 off" -> amounts that are NOT the price
OFF_RE = re.compile(r"(?i)(?:(?:you\s+)?save|saving|take|extra|get|up to)?\s*(?:up to\s*)?" + _CUR + r"\s*(?:off|discount|cashback|cash back|rebate)\b"
                    + r"|(?:(?:you\s+)?save|saving|save up to|extra|take|cashback|rebate|discount of)\s*" + _CUR)
# "$25/mo", "$10 per week", "4 payments of $50", "from $12 a month" -> instalments, not prices
INSTAL_RE = re.compile(r"(?i)(?:\d+\s*(?:x|payments?|instal+ments?|fortnightly payments?)\s*(?:of)?\s*)?" + _CUR
                       + r"\s*(?:/|per|a|each)\s*(?:mo|month|wk|week|fortnight|fn)\b"
                       + r"|\d+\s*(?:x|payments?|instal+ments?)\s*(?:of)?\s*" + _CUR)


# "Bonus $100 gift card", "free $50 voucher", "$20 delivery", "spend $500", "from $9/week" etc. are not the price
GIFT_RE = re.compile(
    r"(?i)(?:(?:bonus|free|get|receive|claim|plus|earn|win|includes?|with|extra)\s+)*" + _CUR + r"\s*(?:bonus\s*)?"
    r"(?:e-?gift\s*cards?|gift\s*cards?|gift\s*vouchers?|vouchers?|store\s*credit|credit|prepaid|cashback|cash\s*back|"
    r"rebate|reward|rewards|points|bonus|gift|coupon|trade[- ]?in|delivery|shipping|postage|freight|installation|"
    r"back|to spend|value|worth)\b"
    r"|(?:e-?gift\s*cards?|gift\s*cards?|vouchers?|store\s*credit|credit|cashback|cash\s*back|rebate|rewards?|bonus|gift|"
    r"trade[- ]?in|delivery|shipping|postage|freight|installation|spend|min(?:imum)?\.?\s*spend|orders? over|"
    r"worth|valued? at|value of|up to|from only|afterpay|zip(?:pay)?|klarna|humm|interest[- ]?free)\W{0,12}" + _CUR,
)


def _drop_savings(vals: list[float]) -> list[float]:
    """vals sorted ascending. Remove an amount that is really the saving (was - now), not a price."""
    if len(vals) == 3:
        a, b, c = vals
        if abs((c - b) - a) <= 0.02 + 0.005 * c:
            return [b, c]
    if len(vals) == 2 and vals[0] < 0.2 * vals[1]:
        return vals[1:]
    return vals


def _pick_prices(text: str) -> list[float]:
    text = GIFT_RE.sub(" ", INSTAL_RE.sub(" ", OFF_RE.sub(" ", SAVE_RE.sub(" ", NOISE_RE.sub(" ", text)))))
    vals = sorted({parse_price(p) for p in PRICE_RE.findall(text)} - {None})
    return _drop_savings([v for v in vals if v > 0])


_SKIP_UP = {"body", "html", "main", "header", "footer", "nav", "[document]"}
_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")


def _capped_text(node, limit: int = 700) -> str | None:
    parts, n = [], 0
    for t in node.stripped_strings:
        n += len(t) + 1
        if n > limit:
            return None
        parts.append(t)
    return " ".join(parts)


_NOISE_RE = re.compile(r"(?is)<(svg|style|iframe)\b[^>]*>.*?</\1\s*>")
_PARSE_SEM = threading.BoundedSemaphore(2)    # parsing holds Python's one-at-a-time lock; 12 parsers at once starve the window


def make_soup(page: str) -> BeautifulSoup:
    """Parse with lxml when installed (several times faster than html.parser); cap huge pages."""
    if len(page) > 1_500_000:
        page = page[:1_500_000]
    if len(page) > 60_000:                               # pictures-as-code, styles and frames never hold products: less to parse
        page = _NOISE_RE.sub("", page)
    try:
        import lxml  # noqa: F401
        soup = BeautifulSoup(page, "lxml")
    except Exception:  # noqa: BLE001
        soup = BeautifulSoup(page, "html.parser")
    return soup


USED_ONLY_STORES = {"Cash Converters"}          # everything they sell is second-hand
USED_RE = re.compile(r"(?i)\b(?:refurb(?:ished)?|pre-?owned|second[- ]?hand|used|open[- ]?box|renewed|ex[- ]?demo|ex[- ]?display|"
                     r"reconditioned|tester|unboxed|grey import|gray import|parallel import|international (?:version|model|stock))\b")
OOS_RE = re.compile(r"(?i)out of stock|sold out|currently unavailable|temporarily unavailable|notify me when|back[- ]?order|"
                    r"coming soon|no longer available|discontinued|unavailable online")


def _first_image(v, base: str) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("url") or v.get("contentUrl")
    if isinstance(v, str) and v.strip() and not v.startswith("data:"):
        return urljoin(base, v.strip())
    return None


_NOT_PHOTO = re.compile(r"(?i)placeholder|blank\.|spacer|loading|pixel|1x1|transparent|no[-_]?image|noimage|default[-_]?image|"
                        r"spinner|lazy\.(?:gif|png)|data:image|\.gif(?:$|\?)")
_NOT_PRODUCT = re.compile(r"(?i)logo|icon|badge|sprite|flag|star|rating|payment|afterpay|zippay|klarna|paypal|banner|"
                          r"promo|award|trustpilot|swatch|avatar|coming[-_]?soon|image[-_]?(?:not|unavailable|missing)|"
                          r"not[-_]?available|missing|fallback|jb[-_]?hi[-_]?fi[-_]?(?:logo|image|default|placeholder)")


def _best_srcset(ss: str, base: str) -> str | None:
    best, best_w = None, -1
    for part in ss.split(","):
        bits = part.strip().split()
        if not bits or bits[0].startswith("data:"):
            continue
        w = 0
        if len(bits) > 1:
            try:
                w = int(float(bits[1].rstrip("wx")) * (1000 if bits[1].endswith("x") else 1))
            except ValueError:
                w = 0
        if w >= best_w:
            best, best_w = bits[0], w
    return urljoin(base, best) if best else None


def _img_url(img, base: str) -> str | None:
    if img is None:
        return None
    cands = []
    pic = img.find_parent("picture")                   # (lxml nests <img> inside <source>, so look up the tree)
    if pic is not None:
        for src in pic.find_all("source", limit=3):
            u = _best_srcset(src.get("srcset") or src.get("data-srcset") or "", base)
            if u:
                cands.append(u)
    for attr in ("data-src", "data-lazy-src", "data-original", "data-lazy", "data-image", "data-img", "data-hi-res-src"):
        v = (img.get(attr) or "").strip()
        if v and not v.startswith("data:"):
            cands.append(urljoin(base, v))
    ss = (img.get("data-srcset") or img.get("srcset") or "").strip()
    if ss:
        u = _best_srcset(ss, base)
        if u:
            cands.append(u)
    v = (img.get("src") or "").strip()
    if v and not v.startswith("data:"):
        cands.append(urljoin(base, v))
    for u in cands:
        path = u.lower().split("?")[0]
        if path.endswith(".svg") or _NOT_PHOTO.search(u):
            continue
        return u
    return None


_BG_URL = re.compile(r"""url\(\s*['"]?([^'")]+)""", re.I)


def image_alternatives(url: str) -> list[str]:
    """Other addresses worth trying if `url` won't load: the real picture behind an image-resizer link
    (/_next/image?url=..., ?url=..., ?src=...), then the same address without resizing parameters."""
    out = []
    try:
        pu = urlparse(url)
        qs = parse_qs(pu.query)
        for k in ("url", "src", "image", "img", "source"):
            if qs.get(k):
                inner = unquote(qs[k][0])
                out.append(urljoin(url, inner))
                break
        if pu.query and not out:
            out.append(url.split("?")[0])
    except ValueError:
        pass
    return [u for u in out if u and u != url]


def _card_image(a, node, base: str) -> str | None:
    """The product photo for a card: skips logos, badges, rating stars and placeholder pixels."""
    seen = set()
    for scope in (a, node):
        for img in scope.find_all("img", limit=8):
            if id(img) in seen:
                continue
            seen.add(id(img))
            hint = " ".join([" ".join(img.get("class") or []), img.get("alt") or "", img.get("id") or ""])
            u = _img_url(img, base)
            if u and not _NOT_PRODUCT.search(hint) and not _NOT_PRODUCT.search(u.rsplit("/", 1)[-1]):
                return u
    for scope in (a, node):                                           # no <img>: a picture set as a CSS background
        for el in scope.find_all(style=True, limit=12):
            m = _BG_URL.search(el.get("style") or "")
            if m and not m.group(1).startswith("data:"):
                u = urljoin(base, _html.unescape(m.group(1)))
                if not u.lower().split("?")[0].endswith(".svg") and not _NOT_PHOTO.search(u):
                    return u
    return None


_PAGE_IMG: dict[str, str | None] = {}


def page_image(url: str) -> str | None:
    """The main picture of a product page (og:image / schema.org image). Used when a card has no usable photo."""
    if url in _PAGE_IMG:
        return _PAGE_IMG[url]
    out = None
    try:
        page = fetch(url, timeout=(4, 7))[:600_000]
        m = (re.search(r'(?i)<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]*content=["\']([^"\']+)', page)
             or re.search(r'(?i)<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', page)
             or re.search(r'(?i)<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)', page))
        if m:
            out = urljoin(url, _html.unescape(m.group(1)))
        else:
            m = re.search(r'(?is)"image"\s*:\s*(?:\[\s*)?"([^"]+)"', page)
            if m:
                out = urljoin(url, m.group(1).replace("\\/", "/"))
    except FetchError:
        pass
    if len(_PAGE_IMG) > 2000:
        _PAGE_IMG.clear()
    _PAGE_IMG[url] = out
    return out


def review_links(o: Offer) -> list[tuple[str, str]]:
    """Places to read reviews of this product."""
    q = keywords_from_title(o.title) or o.title[:60]
    return [("This store's product page", o.url),
            ("ProductReview.com.au", "https://www.productreview.com.au/search?q=" + quote_plus(q)),
            ("Reddit discussions", "https://www.reddit.com/search/?q=" + quote_plus(q + " review")),
            ("Google: reviews in Australia", "https://www.google.com/search?q=" + quote_plus(q + " review australia"))]


def _jsonld_offers(soup: BeautifulSoup, base_url: str, store: str) -> list[Offer]:
    out: list[Offer] = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
            return
        if not isinstance(n, dict):
            return
        t = n.get("@type")
        if "Product" in (t if isinstance(t, list) else [t]) and n.get("name"):
            offers = n.get("offers") or []
            price, url = None, n.get("url")
            for o in offers if isinstance(offers, list) else [offers]:
                if not isinstance(o, dict):
                    continue
                v = o.get("price", o.get("lowPrice"))
                price = parse_price(str(v)) if v is not None else None
                url = url or o.get("url")
                if price:
                    break
            if price and url:
                avail = " ".join(str(o.get("availability", "")) for o in (offers if isinstance(offers, list) else [offers])
                                 if isinstance(o, dict))
                out.append(Offer(store, str(n["name"]), price, urljoin(base_url, url),
                                 image=_first_image(n.get("image"), base_url),
                                 oos=bool(re.search(r"(?i)outofstock|soldout|discontinued|unavailable", avail))))
        for v in n.values():
            if isinstance(v, (dict, list)):
                walk(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(tag.get_text()))
        except (json.JSONDecodeError, TypeError):
            pass
    return out


_BADGE_TXT = re.compile(r"(?i)\b(?:bonus|free|get)\b[^|]{0,30}?(?:gift\s*cards?|vouchers?|e-?gift)\b|\b(?:new|sale|hot|clearance|"
                        r"online only|limited time|best seller|exclusive)\b(?=\s)")


def _best_title(node, a) -> str | None:
    cands = [a.get("title"), a.get("aria-label")]
    for h in node.find_all(["h1", "h2", "h3", "h4", "h5"], limit=2):
        cands.append(h.get_text(" ", strip=True))
    img = a.find("img")
    if img:
        cands.append(img.get("alt"))
    cands.append(a.get_text(" ", strip=True))
    for t in cands:
        t = _BADGE_TXT.sub("", PRICE_RE.sub("", (t or ""))).strip(" -|:")
        t = re.sub(r"\s{2,}", " ", t)
        if 8 <= len(t) <= 200:
            return t
    return None


_P_CLASS = re.compile(r"(?i)price|amount|\bnow\b|special|sale|final|current")
# class names are often BEM/camelCase ("PriceTag_price__strike"), so look for the word after any non-letter, not just \b
_P_WAS = re.compile(r"(?i)(?<![a-z])(?:was|old|rrp|regular|original|orig|compare|list|strike|struck|crossed|slash|ticket|before|previous|msrp|retail)")
_P_BAD = re.compile(r"(?i)save|saving|discount|off\b|instal|afterpay|zip|klarna|humm|gift|bonus|badge|label|promo|offer|"
                    r"reward|points|cashback|rebate|delivery|shipping|finance|per[-_ ]?(?:week|month)|monthly|weekly|"
                    r"trade|voucher|credit|flag|ribbon|sticker|tag\b|callout|banner")


def _structured_price(node) -> tuple[float | None, float | None]:
    """(price, was) read from elements the shop itself marks as price (itemprop, data-price, class='...price...').
    Skips badges, gift cards, instalments and savings. (None, None) when the card doesn't say."""
    now, was, explicit = [], [], []
    for el in node.find_all(True):
        if el.name in ("script", "style"):
            continue
        cls = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
        ip = (el.get("itemprop") or "").lower()
        data = el.get("data-price") or el.get("data-price-amount") or el.get("data-product-price")
        if ip == "price" or data:
            v = parse_price(str(el.get("content") or data or el.get_text(" ", strip=True)))
            if v and v > 0:
                explicit.append(v)                     # explicit machine-readable price wins
            continue
        if not cls.strip() or not _P_CLASS.search(cls):
            continue
        if _P_BAD.search(cls):
            continue
        bad = False
        for p in el.parents:                           # inside a badge / gift-card / instalment wrapper?
            if p is node:
                break
            if _P_BAD.search(" ".join(p.get("class") or [])):
                bad = True
                break
        if bad:
            continue
        if el.find(True, class_=_P_CLASS):             # a wrapper: its children are read on their own
            continue
        txt = el.get_text(" ", strip=True)
        if len(txt) > 40:
            continue
        v = parse_price(txt)
        if not v or v <= 0 or (len(PRICE_RE.findall(txt)) > 1 and not _P_WAS.search(cls)):
            continue
        is_was = bool(_P_WAS.search(cls)) or el.name in ("del", "s", "strike") or any(
            p.name in ("del", "s", "strike") for p in el.parents if p is not node)
        (was if is_was else now).append(v)
    if explicit:
        price = explicit[0]
    elif now:
        # several different "price" figures and none marked as a was-price: the lowest is what you pay, the highest
        # is what it was (shops often mark the crossed-out price with an unusual class name)
        price = min(now)
        if max(now) > price * 1.02:
            was.append(max(now))
    else:
        price = None
    wasv = next((w for w in sorted(was, reverse=True) if price and w > price * 1.02), None)
    return price, wasv


def _heuristic_offers(soup: BeautifulSoup, base_url: str, store: str) -> list[Offer]:
    """Fallback for stores with no structured data: start from each price on the page and walk up to its card."""
    out: list[Offer] = []
    seen: set[str] = set()
    done: set[int] = set()
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for s in soup.find_all(string=PRICE_RE):
        node = s.parent
        for _ in range(7):
            if node is None or node.name in _SKIP_UP:
                break
            if id(node) in done:
                break
            text = _capped_text(node)
            if text is None:
                break
            links = node.find_all("a", href=True)
            hrefs = {l["href"].split("?")[0] for l in links}
            if not links:
                node = node.parent
                continue
            vals = _pick_prices(text)
            if not vals:
                node = node.parent
                continue
            if len(hrefs) > 4 or len(vals) > 3:
                break
            sp, sw = _structured_price(node)
            if sp:                                     # the shop's own price wins; the "was" price comes from its markup
                if not sw:                             # or, failing that, from the card's text (e.g. <s>$1,999</s>, "RRP $2,299")
                    above = [v for v in vals if sp * 1.02 < v <= sp * 4]
                    sw = max(above) if above else None
                vals = sorted({sp, *([sw] if sw else [])})
            done.add(id(node))
            a = next((l for l in links if l["href"].strip() and not l["href"].strip().startswith(("#", "javascript:", "mailto:", "tel:"))), None)
            if a is None:
                break
            title = _best_title(node, a)
            url = urljoin(base_url, a["href"].strip())
            if title and url not in seen:
                seen.add(url)
                was = vals[-1] if len(vals) > 1 and vals[-1] > vals[0] * 1.02 else None
                out.append(Offer(store, title, vals[0], url, was,
                                 image=_card_image(a, node, base_url),
                                 oos=bool(OOS_RE.search(text))))
            break
    return out


def _selector_offers(soup: BeautifulSoup, base_url: str, store: dict) -> list[Offer]:
    out = []
    for card in soup.select(store["item"]):
        t = card.select_one(store["title"])
        p = card.select_one(store["price"])
        a = card.select_one(store.get("link") or "a")
        price = parse_price(p.get_text(" ", strip=True) if p else None)
        if not (t and price and a and a.get("href")):
            continue
        was = None
        if store.get("was_price"):
            w = card.select_one(store["was_price"])
            was = parse_price(w.get_text(" ", strip=True) if w else None)
        out.append(Offer(store["name"], t.get_text(" ", strip=True), price,
                         urljoin(base_url, a["href"]), was, image=_img_url(card.select_one("img"), base_url)))
    return out


# ---- OzBargain: public RSS feeds (the site asks bots to avoid its /search/ and /goto/ pages) ----
OZB_BASE = "https://www.ozbargain.com.au"
_PRICE_T = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)")
_WAS_T = re.compile(r"(?i)(?:rrp|was|normally|usually|valued at|reg(?:ular)?)\s*(?:price\s*)?(?:of\s*)?A?\$\s?(\d[\d,]*(?:\.\d{1,2})?)")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _slug(words: list[str]) -> str:
    return "-".join(w for w in (re.sub(r"[^a-z0-9]+", "", x.lower()) for x in words) if w)


def _parse_expiry(v: str | None) -> float | None:
    if not v:
        return None
    v = v.strip()
    try:
        if v.isdigit():
            n = float(v)
            return n / 1000 if n > 1e11 else n
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(v).timestamp()
    except Exception:  # noqa: BLE001
        pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v)
    return datetime(int(m[1]), int(m[2]), int(m[3]), 23, 59, 59).timestamp() if m else None


def _num(v: str) -> float | None:
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return None


_CODE_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{2,23}$")
_CODE_NO = re.compile(r"(?i)^(none|nil|n/?a|na|no|nocode|tbc|tba|auto|automatic|online|instore|see|gift|giftcard|cashback|cash|apply|click|link)$")


def clean_coupon(v: str | None) -> str:
    """A discount code, or '' if the text isn't clearly one (spaces, words like 'none', or a gift-card/cashback mention)."""
    v = (v or "").strip().strip("\"'`")
    if not v or not _CODE_OK.match(v) or _CODE_NO.match(v):
        return ""
    if re.search(r"(?i)gift|prezzee|cashback|giftcard", v):
        return ""
    return v.upper() if v.isupper() or v.islower() else v


_CODE_IN_TEXT = re.compile(r"(?i:\b(?:promo|coupon|discount|voucher)?\s*code)s?\s*[:\-]?\s*[\"'\u201c]?([A-Z0-9][A-Z0-9_\-]{3,19})\b")
_CODE_STOP = {"FREE", "ONLY", "FOR", "AND", "THE", "USED", "WITH", "ONLINE", "INSTORE", "NONE", "TBC", "TBA", "AUTO", "APPLIED",
              "AUTOMATIC", "NEEDED", "REQUIRED", "THIS", "THAT", "FROM", "WILL", "WHEN", "HERE", "BELOW", "ABOVE", "DEAL", "SALE",
              "OFF", "EXPIRES", "EXPIRED", "ENDS", "NOTE", "NEW", "ALL"}
_NOT_A_CODE = re.compile(r"(?i)gift\s*card|giftcard|e-?gift|prezzee|cash\s*back|cashback|points|\d%\s*back|bank|credit card|"
                         r"visa|mastercard|paypal|afterpay|zip pay")


def text_coupon(title: str, desc: str = "") -> str:
    """A discount code the post itself states, e.g. 'with code SAVE10'. Nothing is returned when the text mentions
    gift cards, cashback or card/bank offers, or when no clear code follows the word 'code'."""
    plain = re.sub(r"<[^>]+>", " ", _html.unescape(f"{title} {desc}"))
    if _NOT_A_CODE.search(plain):
        return ""
    for m in _CODE_IN_TEXT.finditer(plain):
        c = m.group(1)
        if c in _CODE_STOP or not _CODE_OK.match(c):
            continue
        if not any(ch.isdigit() for ch in c) and len(c) < 6:
            continue
        return c
    return ""


def parse_ozb_feed(xml_text: str, now: float | None = None) -> list[Offer]:
    """Live OzBargain deals from an RSS feed. Expired deals are dropped; expiry/votes are kept."""
    now = now or time.time()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[Offer] = []
    for item in root.iter("item"):
        title = link = desc = ""
        meta: dict = {}
        expired, image = False, None
        for ch in item:
            ln = _local(ch.tag)
            if ln == "title":
                title = _html.unescape((ch.text or "").strip())
            elif ln == "link":
                link = (ch.text or "").strip()
            elif ln == "description":
                desc = ch.text or ""
            elif ln == "meta":
                meta = dict(ch.attrib)
            elif ln == "title-msg" and ch.attrib.get("type") == "expired":
                expired = True
            elif ln in ("content", "thumbnail", "enclosure") and ch.attrib.get("url") and not image:
                image = ch.attrib["url"]
        expiry = _parse_expiry(meta.get("expiry"))
        if not title or not link or expired or (expiry and expiry < now):
            continue
        was = None
        wm = _WAS_T.search(title)
        if wm:
            was = _num(wm.group(1))
        plain = SAVE_RE.sub("", _WAS_T.sub("", title))
        pm = _PRICE_T.search(plain)
        price = _num(pm.group(1)) if pm else None
        if not price:
            continue                                   # e.g. "20% off sitewide" - no item price to compare
        merchant = re.search(r"@\s*([^@]+?)\s*$", title)
        store = "OzBargain: " + (merchant.group(1)[:28] if merchant else "deal")
        try:
            votes = int(meta.get("votes-pos", 0)) - int(meta.get("votes-neg", 0))
        except ValueError:
            votes = 0
        out.append(Offer(store, title, price, link, was if was and was > price else None,
                         image=meta.get("image") or image, expires=expiry, votes=votes, source="ozb",
                         coupon=text_coupon(title, desc)))
    return out


def scrape_ozb(store: dict, query: str, full: str | None = None) -> list[Offer]:
    terms = [t for t in parse_keywords(full or query)[0] if t.lower() not in STOP]
    slug = _slug(terms)
    feeds = [f"{OZB_BASE}/deals/feed"]
    if slug:
        feeds += [f"{OZB_BASE}/tag/{slug}/feed", f"{OZB_BASE}/product/{slug}/feed"]
    for t in terms[:3]:
        one = _slug([t])
        if len(one) >= 3 and not one.isdigit() and one != slug:
            feeds.append(f"{OZB_BASE}/tag/{one}/feed")
    # A busy tag (like "garmin" in Black Friday week) fills the first page of its feed with the newest posts, pushing
    # slightly older live deals off it, so also read the second page of the two most specific tags.
    tags = [f for f in feeds if "/tag/" in f]
    feeds += [t + "?page=1" for t in tags[:2]]
    out, seen, ok, last = [], set(), False, None
    for url in dict.fromkeys(feeds):
        try:
            text = fetch_cached(url, ttl=600, accept="application/rss+xml,application/xml,text/xml,*/*", ua=OZB_UA)
        except FetchError as e:
            last = e                                   # an unknown tag is a normal 404 - keep going
            continue
        ok = True
        for o in parse_ozb_feed(text):
            if o.url not in seen:
                seen.add(o.url)
                out.append(o)
    if not ok and last:
        raise last
    return out


# ---- StaticICE: Australian price comparison across 200+ retailers (plain server-rendered HTML) ----
def _staticice_offers(page: str, base_url: str) -> list[Offer]:
    soup = make_soup(page)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "redirect.cgi" not in href or "linkid=2" not in href or not a.get_text(strip=True).startswith("$"):
            continue
        q = parse_qs(urlparse(href).query)
        url = (q.get("newurl") or [""])[0]
        merchant = (q.get("name") or ["StaticICE"])[0]
        price = parse_price(a.get_text(strip=True))
        if not price or not url.startswith("http") or url in seen:
            continue
        parts = []
        for el in a.next_elements:                     # description = text between price link and store link
            if getattr(el, "name", None) == "a" and "redirect.cgi" in (el.get("href") or ""):
                break
            if el.name is None and not any(par is a for par in el.parents):
                t = str(el).strip()
                if t:
                    parts.append(t)
        desc = " ".join(parts).strip()
        if not desc:
            m = re.search(r"latest price for (.+?)(?:\.\.\.)?$", a.get("title", ""))
            desc = m.group(1) if m else ""
        if desc:
            seen.add(url)
            out.append(Offer(merchant, desc, price, url, source="staticice"))
    return out


def _amazon_offers(soup, base_url: str) -> list[Offer]:
    """Amazon search results, read from Amazon's own markup: every result is a div[data-component-type=s-search-result];
    the price you pay is the first .a-price, the crossed-out RRP is the .a-price.a-text-price. (The general reader was
    picking up pieces like '. 99 RRP' as titles, and the sponsored click-through links.)"""
    out, seen = [], set()
    stats = {"cards": 0, "noprice": 0, "fromprice": 0, "titles_noprice": [], "all": []}
    AMAZON_STATS.clear()
    AMAZON_STATS.update(stats)
    for card in soup.select('div[data-component-type="s-search-result"]'):
        asin = (card.get("data-asin") or "").strip()
        if not asin or asin in seen:
            continue
        h2 = card.find("h2")
        title = ""
        if h2 is not None:
            title = (h2.get("aria-label") or h2.get_text(" ", strip=True) or "").strip()
        img0 = card.select_one("img.s-image")
        alt = re.sub(r"\s+", " ", (img0.get("alt") if img0 is not None else "") or "").strip()
        if not title or (len(title) < 25 and len(alt) > len(title) + 8):
            title = alt or title           # some cards show only the brand ("COROS") as heading; the picture label has the full name
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 4:
            continue
        price = was = None
        for el in card.select("span.a-price"):
            off = el.select_one("span.a-offscreen")
            v = parse_price(off.get_text(strip=True) if off is not None else el.get_text(" ", strip=True))
            if not v or v <= 0:
                continue
            if "a-text-price" in (el.get("class") or []) or el.get("data-a-strike") == "true":
                was = was or v
            elif price is None:
                price = v
        stats["cards"] += 1
        if len(stats["all"]) < 70:
            stats["all"].append(f"{asin} {('$%.2f' % price) if price else 'no price'}  {title[:75]}")
        if price is None:
            # items with several sellers or options often show no big price - only "from $399.00" or "Options: ... from $399"
            m = re.search(r"(?i)(?:from|options?:[^$]{0,40}from|see (?:all )?(?:buying )?options)[^$]{0,20}\$\s*([\d,]+(?:\.\d\d)?)",
                          card.get_text(" ", strip=True))
            price = parse_price(m.group(1)) if m else None
            if price:
                stats["fromprice"] += 1
        if price is None:
            stats["noprice"] += 1
            if len(stats["titles_noprice"]) < 8:
                stats["titles_noprice"].append(title[:70])
            continue
        if was is not None and was <= price * 1.02:
            was = None
        img = card.select_one("img.s-image")
        seen.add(asin)
        out.append(Offer("Amazon AU", title, price, urljoin(base_url, f"/dp/{asin}"), was,
                         image=(img.get("src") if img is not None else None),
                         oos=bool(re.search(r"(?i)currently unavailable|temporarily out of stock", card.get_text(" ", strip=True)))))
    AMAZON_STATS.update(stats)
    return out


AMAZON_STATS: dict = {}

# Shops built on Shopify draw their search results with JavaScript, so the page looks empty. Shopify also gives every
# shop two plain data feeds (search suggestions and the full product list) - read those instead.
SHOPIFY_HOSTS = {"sihoo.com.au", "hardybrothers.com.au", "myperfumeshop.com.au"}


def _shopify_offers(store: dict, base: str, query: str) -> list[Offer]:
    from urllib.parse import urlparse
    root = f"https://{urlparse(base).hostname}"
    name, out = store["name"], []

    def add(title, vendor, handle, price, was, image, avail):
        p = parse_price(str(price)) if price not in (None, "") else None
        if not title or not p or p <= 0:
            return
        if vendor and vendor.lower() not in title.lower():
            title = f"{vendor} {title}"                # "M57 Pro Ergonomic Office Chair" -> "SIHOO M57 Pro ..."
        w = parse_price(str(was)) if was not in (None, "", "0", 0, "0.00") else None
        if w is not None and w <= p * 1.02:
            w = None
        if isinstance(image, dict):
            image = image.get("src") or image.get("url")
        if isinstance(image, str) and image.startswith("//"):
            image = "https:" + image
        out.append(Offer(name, title, p, f"{root}/products/{handle}", w, image=image or None, oos=avail is False))

    try:
        data = json.loads(fetch(f"{root}/search/suggest.json?q={quote_plus(query)}&resources[type]=product&resources[limit]=10",
                                accept="application/json"))
        for pr in ((data.get("resources") or {}).get("results") or {}).get("products") or []:
            handle = pr.get("handle") or str(pr.get("url", "")).split("/products/")[-1].split("?")[0]
            add(pr.get("title"), pr.get("vendor"), handle, pr.get("price"), pr.get("compare_at_price_max") or pr.get("compare_at_price"),
                pr.get("featured_image") or pr.get("image"), pr.get("available"))
    except (FetchError, ValueError, AttributeError):
        out = []
    if out:
        return out
    data = json.loads(fetch(f"{root}/products.json?limit=250", accept="application/json"))     # small shops: the whole range
    for pr in data.get("products") or []:
        vs = [v for v in pr.get("variants") or [] if parse_price(str(v.get("price"))) ]
        if not vs:
            continue
        ok = [v for v in vs if v.get("available")] or vs
        v = min(ok, key=lambda x: parse_price(str(x.get("price"))))
        imgs = pr.get("images") or []
        add(pr.get("title"), pr.get("vendor"), pr.get("handle"), v.get("price"), v.get("compare_at_price"),
            imgs[0] if imgs else None, bool(v.get("available")))
    return out


def _parse_store_page(page: str, url: str, store: dict) -> list[Offer]:
    with _PARSE_SEM:
        return _parse_store_page_now(page, url, store)


def _parse_store_page_now(page: str, url: str, store: dict) -> list[Offer]:
    soup = make_soup(page)
    if store.get("item"):
        return _selector_offers(soup, url, store)
    if "amazon.com" in url:
        got = _amazon_offers(soup, url)
        if got:
            for o in got:
                o.store = store["name"]
            return got
    return _jsonld_offers(soup, url, store["name"]) or _heuristic_offers(soup, url, store["name"])


def scrape_store(store: dict, query: str, cfg: dict | None = None, full: str | None = None) -> list[Offer]:
    """All products found for `query` (before relevance ranking). Raises FetchError(kind) with the reason.
    Stores that block plain requests or build their pages with JavaScript are loaded in a real browser."""
    tpl, cfg = store.get("alt_url") or store["search_url"], cfg or {}
    if tpl.startswith("ozb:"):
        _step("Reading the OzBargain feed")
        return scrape_ozb(store, query, full)
    if any(h in tpl for h in SHOPIFY_HOSTS):
        _step("Reading the shop's product list")
        return _shopify_offers(store, tpl, full or query)
    if "staticice." in tpl:
        _step("Loading the price-comparison results")
        inc, exc = parse_keywords(full or query)
        url = tpl.replace("{query}", quote_plus(" ".join(inc + ["-" + x for x in exc]))) + "&links=40"
        page = fetch(url)
        offers = _staticice_offers(page, url)
        if not offers and _classify_empty(page):
            raise FetchError(_classify_empty(page), "no products")
        return offers

    url = tpl.replace("{query}", quote_plus(query))
    use_b, rendered = browser_wanted(cfg), False
    if store.get("use_browser") and use_b:
        _step("Opening the hidden browser and loading the page")
        page, rendered = BROWSER.render(url), True
    else:
        try:
            _step("Loading the search page")
            page = fetch(url)
        except FetchError as e:
            if e.kind != "blocked" or not use_b:
                raise
            _step("The shop refused a plain visit - trying the hidden browser")
            page, rendered = BROWSER.render(url), True            # blocked for scripts: try as a real browser
    _step("Reading prices from the page")
    offers = _parse_store_page(page, url, store)
    if not offers and not rendered:
        kind = _classify_empty(page) or ("needsjs" if _looks_js(page) else None)
        if kind:
            if not use_b:
                raise FetchError("needsjs" if kind == "needsjs" else kind, kind)
            _step("No prices in the page - rebuilding it in the hidden browser")
            page, rendered = BROWSER.render(url), True
            offers = _parse_store_page(page, url, store)
    if not offers and rendered and use_b and _classify_empty(page) == "botcheck":
        try:                                                      # one more go, behaving like a visitor who browsed in
            _step("A bot check appeared - retrying like a normal visitor")
            page = BROWSER.render(url, 25, warm=True)
            offers = _parse_store_page(page, url, store)
        except FetchError:
            pass
    _step("Checking what came back")
    if not offers:
        kind = _classify_empty(page)
        if kind:
            raise FetchError(kind, kind)
    if rendered and offers:
        store["_browser_used"] = True
    if getattr(_AUDIT, "on", False):
        _AUDIT.page = page
    return offers


_AUDIT = threading.local()
AUDIT_SHOPS = ("jb hi-fi", "bing lee", "betta home", "amazon")


def price_audit(cfg: dict | None = None, names=AUDIT_SHOPS, per_shop: int = 6, deadline: float = 45.0) -> str:
    """For diagnostics: for a few shops whose prices have been wrong, run a sample search and record what Deals read
    (title, price, was-price) next to the shop's own markup around that product, so the price rules can be fixed
    from real pages instead of guesses."""
    con = db()
    rows = [dict(r) for r in con.execute("SELECT * FROM stores WHERE enabled=1")]
    picks = [r for r in rows if any(n in r["name"].lower() for n in names)]

    def one(st):
        _AUDIT.on, _AUDIT.page = True, ""
        q = sample_query(st)
        out = [f"=== {st['name']}  (search: {q})  {st['search_url']}"]
        try:
            offers = scrape_store(dict(st), q, cfg, q)
            page = getattr(_AUDIT, "page", "") or ""
            out.append(f"{len(offers)} products read, page {len(page)} bytes, via browser: {bool(st.get('_browser_used'))}")
            for o in offers[:per_shop]:
                out.append(f"- READ: ${o.price}  was={o.was_price}  {o.title[:80]}  {o.url[:100]}")
                i = page.find(o.title[:30]) if o.title else -1
                if i < 0:
                    i = page.find(o.url.split("//", 1)[-1].split("/", 1)[-1][:40])
                if i >= 0:
                    snip = re.sub(r"\s+", " ", page[max(0, i - 300): i + 1300])
                    out.append("  MARKUP: " + snip)
                else:
                    out.append("  (could not find this product in the page text)")
        except Exception as e:  # noqa: BLE001
            out.append(f"failed: {type(e).__name__}: {str(e)[:120]}")
        finally:
            _AUDIT.on = False
        return "\n".join(out)

    texts = []
    ex = ThreadPoolExecutor(max_workers=4)
    futs = {ex.submit(one, st): st for st in picks}
    try:
        done, notdone = wait(list(futs), timeout=deadline)
        for fut in done:
            texts.append(fut.result())
        texts += [f"=== {futs[f]['name']}: still running after {deadline:.0f}s, skipped" for f in notdone]
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return "\n\n".join(texts) or "(none of the audited shops are turned on)"


_HOST_SEMS: dict = {}
_HOST_LOCK = threading.Lock()
_SCAN_CACHE: dict = {}
_SITE_FAIL: dict = {}


def reset_site_failures() -> None:
    """Forget 'this site just failed' memories, e.g. after you verified a shop in the browser."""
    with _HOST_LOCK:
        _SITE_FAIL.clear()
        _SCAN_CACHE.clear()
SCAN_TTL = 300
FAIL_TTL = 90           # a site that just failed isn't asked again for other watchlist items within 90 seconds          # the same search at the same store within 5 minutes is answered from memory


def _host_sem(store: dict):
    """At most 2 requests at a time to any one site, however many items are being checked."""
    host = urlparse(store["search_url"].replace("{query}", "x")).netloc or store["name"]
    with _HOST_LOCK:
        return _HOST_SEMS.setdefault(host, threading.Semaphore(2))


def lower_priority():
    """Run below normal priority so scans never starve other programs (Windows only; browser children inherit it)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)      # BELOW_NORMAL_PRIORITY_CLASS
    except Exception:  # noqa: BLE001
        pass


def _scan_one(store: dict, keywords: str, cfg: dict | None = None):
    key = (store["search_url"], keywords, (cfg or {}).get("browser", "1"))
    now = time.time()
    with _HOST_LOCK:
        hit = _SCAN_CACHE.get(key)
    if hit and now - hit[0] < SCAN_TTL:
        store["_browser_used"] = hit[3]
        return store, [replace(o) for o in hit[1]], hit[2]
    host = urlparse(store["search_url"].replace("{query}", "x")).netloc
    with _HOST_LOCK:
        bad = _SITE_FAIL.get(host)
    if bad and now - bad[0] < FAIL_TTL:
        return store, [], bad[1]
    err, offers = None, []
    t_start = time.time()
    with _host_sem(store):
        with _HOST_LOCK:                                  # it may have failed while we waited our turn
            bad = _SITE_FAIL.get(host)
        if bad and time.time() - bad[0] < FAIL_TTL:
            err = bad[1]
        else:
            try:
                offers = scrape_store(store, search_query(keywords), cfg, keywords)
                if store.get("_browser_used") and not store.get("use_browser") and store.get("id"):
                    try:
                        con = db()
                        con.execute("UPDATE stores SET use_browser=1 WHERE id=?", (store["id"],))
                        con.commit()
                        store["use_browser"] = 1
                    except Exception:  # noqa: BLE001
                        pass
            except FetchError as e:
                err = e.kind
            except Exception:  # noqa: BLE001
                err = "error"
    store["_ms"] = int((time.time() - t_start) * 1000)
    with _HOST_LOCK:
        if len(_SCAN_CACHE) > 120:                       # each entry holds a shop's whole result list: let old ones go
            for k in [k for k, v in list(_SCAN_CACHE.items()) if now - v[0] >= SCAN_TTL]:
                _SCAN_CACHE.pop(k, None)
        if len(_SCAN_CACHE) > 400:
            _SCAN_CACHE.clear()
        _SCAN_CACHE[key] = (now, [replace(o) for o in offers], err, bool(store.get("_browser_used")))
        if err in ("blocked", "notfound", "error", "botcheck", "needsjs", "nobrowser"):
            _SITE_FAIL[host] = (time.time(), err)
    return store, offers, err


STATUS_LABELS = {"blocked": "Blocked by site (bot protection)", "notfound": "Search URL not found",
                 "botcheck": "Bot-check page shown", "needsjs": "Needs JavaScript - turn on browser mode",
                 "nobrowser": "Browser engine unavailable"}


def status_text(raw_count: int, err: str | None, via_browser: bool = False) -> str:
    if err:
        return STATUS_LABELS.get(err, "Error / unreachable")
    if not raw_count:
        return "No products found"
    return f"Working via browser ({raw_count} products)" if via_browser else f"Working ({raw_count} products)"


def status_mark(status: str) -> str:
    """v = working, - = untested, x = failing"""
    return "v" if status.startswith("Working") else "-" if status in ("Not tested", "") else "x"


# --------------------------------------------------------------------------- #
# Relevance ranking (Google-style): partial matches allowed, accessories pushed down
# --------------------------------------------------------------------------- #
STOP = {"the", "a", "an", "and", "or", "of", "with", "for", "new", "in", "to", "on"}
STRONG_ACC = {"band", "bands", "strap", "straps", "wristband", "wristbands", "protector", "protectors",
              "replacement", "refill", "refills", "compatible", "lanyard", "buckle", "tempered",
              "sample", "samples", "decant", "vial", "atomiser", "atomizer", "dupe", "replica"}
WEAK_ACC = {"case", "cases", "cover", "covers", "skin", "sleeve", "pouch", "stand", "mount", "holder",
            "dock", "cable", "cord", "charger", "adapter", "film", "clip", "box", "winder", "bracket",
            "tray", "bag"}
CUT = {"with", "w", "incl", "includes", "including", "plus", "bundle"}   # "...Watch with Sport Band"
FOR = {"for", "compatible"}                                              # "Band for Apple Watch"


SYNONYMS = {"band": ["strap", "wristband"], "strap": ["band", "wristband"], "wristband": ["band", "strap"],
            "laptop": ["notebook"], "notebook": ["laptop"], "tv": ["television"], "television": ["tv"],
            "phone": ["smartphone"], "smartphone": ["phone"], "earbuds": ["earphones"], "earphones": ["earbuds"],
            "headphones": ["headphone"], "headphone": ["headphones"]}


def tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def _has_digit(s: str) -> bool:
    return any(ch.isdigit() for ch in s)


def _term_index(term: str, toks: list[str]) -> int:
    nt = norm(term)
    if not nt:
        return -1
    digits = _has_digit(nt)
    for i, t in enumerate(toks):
        if t == nt:
            return i
        if not digits and t in ("smart" + nt, "wrist" + nt):   # smartwatch, wristwatch, smartphone
            return i
        if not digits and len(nt) >= 3 and t.startswith(nt) and (len(nt) >= 5 or len(t) - len(nt) <= 2):
            return i                     # a short word ('pro', 'max', 'air') only matches itself + a plural, not 'protective' / 'airpods'
        if not digits and len(t) >= 3 and nt.startswith(t) and len(nt) - len(t) <= 2:
            return i
    for i in range(len(toks)):           # 'wh-1000xm5' -> tokens 'wh' + '1000xm5'
        cat = ""
        for j in range(i, min(i + 4, len(toks))):
            cat += toks[j]
            if cat == nt:
                return i
            if len(cat) >= len(nt):
                break
    return -1


MODEL_ALIASES = {"ps5": ["playstation5"], "ps4": ["playstation4"], "xsx": ["seriesx"], "xss": ["seriess"]}


def _model_index(term: str, prev: str | None, toks: list[str]) -> int:
    """Find a model number such as '6' in a title written 'Watch 6', 'Watch6' or '6th'.
    Different numbers never match: '6' does not match 'Watch5', 'iPhone 16' or 'Series 8'."""
    nt = norm(term)
    if prev and not _has_digit(prev):                  # "watch" + "6" -> the title word "watch6"
        i = _term_index(norm(prev) + nt, toks)
        if i >= 0:
            return i
    for alt in MODEL_ALIASES.get(nt, []):
        i = _term_index(alt, toks)
        if i >= 0:
            return i
    if nt.isdigit():                                   # "2" -> "2nd gen"
        for i, t in enumerate(toks):
            if re.fullmatch(nt + r"(st|nd|rd|th)", t):
                return i
    return -1


def _acc_kind(t: str) -> int:
    if t in STRONG_ACC:
        return 2
    if t in WEAK_ACC:
        return 1
    for suf in ("band", "bands", "strap", "straps"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            return 2
    for suf in ("case", "cases", "cover", "covers"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            return 1
    return 0


BRANDS = {
    "apple", "samsung", "sony", "bose", "lg", "dell", "hp", "lenovo", "asus", "acer", "msi", "microsoft",
    "google", "amazon", "logitech", "razer", "corsair", "jbl", "sennheiser", "anker", "garmin", "fitbit",
    "casio", "fossil", "seiko", "citizen", "huawei", "xiaomi", "oneplus", "nokia", "motorola", "nintendo",
    "canon", "nikon", "fujifilm", "gopro", "dji", "panasonic", "philips", "dyson", "lego", "tcl", "hisense",
    "sharp", "toshiba", "seagate", "sandisk", "kingston", "nvidia", "amd", "intel", "tplink", "netgear",
    "ubiquiti", "belkin", "ugreen", "baseus", "oppo", "realme", "beats", "skullcandy", "sonos", "jabra",
    "tissot", "timex", "withings", "suunto", "coros", "amazfit", "ticwatch", "mobvoi", "benq", "viewsonic",
    "aoc", "gigabyte", "asrock", "evga", "steelseries", "hyperx", "elgato", "wacom", "brother", "epson",
    "roborock", "eufy", "arlo", "wyze", "tapo", "ecovacs", "breville", "nespresso", "delonghi", "kogan",
}
# product-line words that imply a brand ("iphone" -> Apple)
BRAND_ALIASES = {
    "iphone": "apple", "ipad": "apple", "macbook": "apple", "airpods": "apple", "airpod": "apple",
    "imac": "apple", "airtag": "apple", "galaxy": "samsung", "pixel": "google", "kindle": "amazon",
    "alexa": "amazon", "playstation": "sony", "ps5": "sony", "ps4": "sony",
    "xbox": "microsoft", "thinkpad": "lenovo", "ideapad": "lenovo",
    "rog": "asus", "zenbook": "asus", "vivobook": "asus", "inspiron": "dell", "xps": "dell", "alienware": "dell", "forerunner": "garmin", "fenix": "garmin", "vivoactive": "garmin", "gshock": "casio",
    "airpodspro": "apple", "quietcomfort": "bose", "walkman": "sony", "bravia": "sony", }


def _query_brand_groups(kept: list[str]) -> list[str]:
    """Brand words the title must contain (any one) - empty when the search names no brand."""
    accept: list[str] = []
    for t in kept:
        n = norm(t)
        if n in BRANDS:
            accept.append(n)
        elif n in BRAND_ALIASES:
            accept += [BRAND_ALIASES[n], n]
    return accept


def query_brands(keywords: str) -> list[str]:
    """Brands named (or implied) by the search, for display, e.g. ['Apple']."""
    kept = [t for t in parse_keywords(keywords)[0] if t.lower() not in STOP]
    out: list[str] = []
    for t in kept:
        n = norm(t)
        b = n if n in BRANDS else BRAND_ALIASES.get(n)
        if b and b.title() not in out:
            out.append(b.title() if b not in ("lg", "hp", "msi", "tcl", "aoc", "amd", "dji", "jbl") else b.upper())
    return out


def rank_offers(keywords: str, offers: list[Offer]) -> list[Offer]:
    """Score every offer for relevance to the keywords (0-100), flag accessories, sort best first."""
    terms, excl = parse_keywords(keywords)
    kept = [t for t in terms if t.lower() not in STOP] or terms
    if not kept:
        return []
    qtoks = set(tokens(" ".join(kept)))
    brand_ok = _query_brand_groups(kept)               # empty = no brand named, show every brand
    shopping_acc = any(_acc_kind(t) for t in qtoks)   # "watch band": accessories are what they want
    weights = [2 if _has_digit(t) else 1 for t in kept]
    cands, seen = [], set()
    for o in offers:
        if o.url in seen:
            continue
        seen.add(o.url)
        nt = norm(o.title)
        if any(norm(x) and norm(x) in nt for x in excl):
            continue
        toks = tokens(o.title)
        if not toks:
            continue
        if brand_ok and not any(_term_index(b, toks) >= 0 for b in brand_ok):
            continue                                   # a different brand - not what was searched for
        idxs = []
        for k, t in enumerate(kept):
            i = _term_index(t, toks)
            for alt in SYNONYMS.get(t.lower(), []) if i < 0 else []:
                i = _term_index(alt, toks)
                if i >= 0:
                    break
            if i < 0 and _has_digit(t):
                i = _model_index(t, kept[k - 1] if k else None, toks)
            idxs.append(i)
        if any(i < 0 and _has_digit(t) for t, i in zip(kept, idxs)):
            continue                                   # a model number was searched for and this isn't it
        cov = sum(w for i, w in zip(idxs, weights) if i >= 0) / sum(weights)
        if (len(kept) == 1 and idxs[0] < 0) or cov < 0.5:
            continue
        sc = 60 * cov
        matched = [i for i in idxs if i >= 0]
        sc += 12 * (1 - min(matched) / len(toks))      # query words early in the title
        if len(matched) == len(kept) and matched == sorted(matched) and max(matched) - min(matched) <= len(kept) + 1:
            sc += 8                                    # words together, in order
        if idxs[0] == 0:
            sc += 5
        sc -= min(10, max(0, len(toks) - 14) * 0.5)    # keyword-stuffed titles
        cut = next((i for i, t in enumerate(toks) if t in CUT and i > 0), len(toks))
        kind = 0 if shopping_acc else max((_acc_kind(t) for t in toks[:cut] if t not in qtoks), default=0)
        f = next((i for i, t in enumerate(toks) if t in FOR and i > 0), None)
        for_flag = (not shopping_acc) and f is not None and min(matched) > f  # query words only after "for"
        cands.append([o, sc, kind, for_flag])

    clean = sorted(c[0].price for c in cands if c[2] == 0 and not c[3])
    pool = clean if len(clean) >= 2 else sorted(c[0].price for c in cands)
    med = pool[len(pool) // 2] if pool else 0.0
    n = len(cands)
    for c in cands:
        o, sc, kind, for_flag = c
        acc = for_flag
        if not acc and kind == 2:
            acc = n < 4 or o.price < 0.6 * med
        elif not acc and kind == 1:
            acc = n >= 4 and o.price < 0.35 * med
        if acc:
            sc -= 45
        elif n >= 4 and med and o.price < 0.15 * med:
            sc -= 10
        o.score, o.accessory = max(0.0, min(100.0, sc)), acc
    return sorted((c[0] for c in cands), key=lambda o: (-o.score, o.price))


def apply_ozb_discount(offers: list[Offer]) -> list[Offer]:
    """Keep an OzBargain deal only if it is discounted: the post gives an RRP/was price, or it beats the
    typical price at other shops by 5%+. With nothing to compare against, a well-voted (10+) deal is kept."""
    pool = sorted(o.price for o in offers if o.source != "ozb" and not o.accessory and o.score >= ALERT_MIN_SCORE)
    ref = pool[len(pool) // 2] if len(pool) >= 2 else None
    keep = []
    for o in offers:
        if o.source != "ozb" or o.accessory:
            keep.append(o)
        elif o.was_price and o.was_price > o.price:
            keep.append(o)
        elif ref and o.price <= 0.95 * ref:
            o.ref_price = ref
            keep.append(o)
        elif not ref and o.votes >= 10:
            keep.append(o)
    return keep


def deal_pct(o: Offer, prev: float | None = None) -> tuple[float | None, str | None]:
    """(percent off, kind) when an offer is a real discount, else (None, None).
    kinds: markdown (shop lists a was-price) | below (OzBargain vs other shops) | dropped (cheaper than last
    time we saw it) | ozb (a vetted OzBargain deal with nothing to compare against)."""
    if o.was_price and o.was_price > o.price:
        return 100 * (o.was_price - o.price) / o.was_price, "markdown"
    if o.ref_price and o.ref_price > o.price:
        return 100 * (o.ref_price - o.price) / o.ref_price, "below"
    if prev and prev > o.price * 1.03:
        return 100 * (prev - o.price) / prev, "dropped"
    if o.source == "ozb":
        return 0.0, "ozb"
    return None, None


def order_offers(offers: list[Offer], sort: str = "Best match", hide_acc: bool = False, limited: bool = False,
                 prev: dict | None = None, hide_used: bool = False, value_key=None) -> tuple[list[Offer], list[Offer]]:
    """Split ranked offers into (deals, regular prices) and order each by the chosen sort."""
    rows = [o for o in offers if not (hide_acc and o.accessory) and not (hide_used and o.used)]
    if limited:
        rows = [o for o in rows if o.expires]
    prev = prev or {}
    info = {id(o): deal_pct(o, prev.get(o.url)) for o in rows}
    deals = [o for o in rows if info[id(o)][1] and not o.used and not o.oos]
    others = [o for o in rows if not (info[id(o)][1] and not o.used and not o.oos)]
    others.sort(key=lambda o: o.oos)                   # out-of-stock items sink to the bottom (stable sort)

    def pct(o):
        return info[id(o)][0] or 0.0

    if sort == "Price: low to high":
        key = lambda o: o.price
    elif sort == "Price: high to low":
        key = lambda o: -o.price
    elif sort == "Biggest discount":
        key = lambda o: (-pct(o), o.price)
    elif sort == "Ending soon":
        key = lambda o: (o.expires is None, o.expires or 0, -o.score)
    elif sort in ("Best value", "Deal score") and value_key:
        key = lambda o: (o.oos, value_key(o))
    else:                                              # best match: strong, non-accessory deals first, biggest cut first
        deals.sort(key=lambda o: (o.accessory or o.score < ALERT_MIN_SCORE, -pct(o), -o.score))
        return deals, others
    deals.sort(key=key)
    others.sort(key=lambda o: (o.oos, key(o)))
    return deals, others


JUNK_RATIO = 0.10      # a listing priced 90%+ below the typical price is treated as irrelevant


class Report(list):
    """Per-store results (a plain list) that also says how many listings were filtered out."""
    paused_names: tuple = ()   # which of those would otherwise have been searched for this query
    paused = 0     # stores skipped because they keep failing (retried every day or so)
    skipped = 0    # stores not searched because they do not sell this kind of product
    timed_out = 0  # stores that didn't answer within the time limit
    junk = 0       # too cheap to be the thing searched for (cases, stickers, parts...)
    hidden = 0     # from sites you've chosen to hide (eBay by default)
    widened = False  # a thin search was automatically widened to every shop
    words: dict = {}  # word -> how many listings (before filtering) used it
    ozb_titles: list = []      # what the OzBargain feeds returned (for the developer report)
    hidden_offers: list = []   # (offer, reason) for listings kept out of the results: "reported" | "site" | "cheap"
    second_tried = 0           # slow shops given a second go after the first results were shown
    second_added = 0           # listings that second go found


def blocked_words(cfg: dict | None) -> list[str]:
    raw = (cfg or {}).get("blocked", DEFAULTS["blocked"]) or ""
    return [w.strip().lower() for w in raw.split(",") if w.strip() and w.strip().lower() != "none"]


def is_hidden_offer(o: Offer, words: list[str]) -> bool:
    if o.source == "ozb":                          # community posts are vetted by OzBargain, even ones that point at eBay
        return False
    host = urlparse(o.url).netloc.lower()
    label = f"{o.store} {host}".lower()
    return any(w in label for w in words)


def drop_junk_prices(offers: list[Offer], ratio: float = JUNK_RATIO) -> tuple[list[Offer], int]:
    """Drop listings priced under `ratio` x the typical (median) price of the strong matches.
    Needs 3+ strong matches to know what 'typical' is."""
    pool = sorted(o.price for o in offers if o.score >= ALERT_MIN_SCORE and not o.accessory and not o.used)
    if len(pool) < 3:
        return offers, 0
    base = pool[len(pool) // 2]
    keep = [o for o in offers if o.price >= base * ratio]
    return keep, len(offers) - len(keep)


POOL_WORKERS = 12


def _scan_order(st: dict, cats: set) -> tuple:
    """Who gets searched first. The queue used to run in alphabetical order, so when time ran out the shops
    from G to Z (Mwave, Scorptec, Umart, StaticICE...) never got a turn. Now: price-comparison sites, then shops that
    sell this kind of product, then the rest - and quick plain-web shops before the ones needing the slow browser."""
    url = (st.get("search_url") or "") + (st.get("alt_url") or "")
    sc = set((st.get("cats") or "all").split())
    if "staticice." in url or "getprice." in url or url.startswith("ozb:"):
        tier = 0
    elif cats and sc & cats:
        tier = 1
    elif sc & {"all", "general"}:
        tier = 2
    else:
        tier = 3
    return (tier, st.get("name", ""))


def _is_marketplace(st: dict) -> bool:
    """Shops that carry almost everything (Amazon...). They go first in the slow browser lane and the search waits for them."""
    return "amazon." in (st.get("search_url") or "").lower()
# The big, well-known shops are always tried, even after repeated failures: people expect to see them, and a block
# on them is often temporary.
ALWAYS_TRY = {"jb hi-fi", "harvey norman", "bing lee", "the good guys", "officeworks", "kogan", "myer", "david jones",
              "big w", "target au", "bunnings", "woolworths", "coles", "chemist warehouse", "kmart", "costco au",
              "amazon au", "catch", "betta home living", "appliances online", "rebel sport", "mwave", "scorptec", "umart"}
DEAD_AFTER = 3          # a store that fails this many times in a row is paused for a day (then 2, 4, 7 days)
FAIL_KINDS = {"blocked", "notfound", "needsjs", "botcheck", "nobrowser", "error"}


def record_health(con, store_id, ok: bool, kind: str | None = None):
    """Track consecutive failures so searches stop wasting time on stores that never work."""
    row = con.execute("SELECT fail_streak FROM stores WHERE id=?", (store_id,)).fetchone() if store_id else None
    if not row:
        return
    if ok:
        streak, skip = 0, 0.0
    elif kind is None or kind in FAIL_KINDS:
        streak = (row["fail_streak"] or 0) + 1
        skip = time.time() + min(7, 2 ** max(0, streak - DEAD_AFTER)) * 86400 if streak >= DEAD_AFTER else 0.0
    else:
        return
    con.execute("UPDATE stores SET fail_streak=?, skip_until=? WHERE id=?", (streak, skip, store_id))


def reset_health(con):
    con.execute("UPDATE stores SET fail_streak=0, skip_until=0")
    con.commit()


# Stores whose search pages are built by JavaScript and have shown the wrong figure as the price. For these, each
# product's own page is read for the price the shop publishes in its page tags - that one is always the real price.
VERIFY_STORES = ("jb hi-fi", "jbhifi", "bing lee", "binglee", "betta")
_PAGE_PRICE_CACHE: dict[str, tuple[float, float | None]] = {}


def page_price(html: str) -> float | None:
    """The price a product page publishes about itself (og:price / product:price meta, itemprop, JSON-LD). None if unsure."""
    soup = make_soup(html)
    for m in soup.find_all("meta"):
        key = (m.get("property") or m.get("name") or m.get("itemprop") or "").lower()
        if key in ("og:price:amount", "product:price:amount", "product:sale_price:amount", "price"):
            v = parse_price(str(m.get("content") or ""))
            if v and v > 0:
                return v
    el = soup.find(attrs={"itemprop": "price"})
    if el is not None:
        v = parse_price(str(el.get("content") or el.get_text(" ", strip=True)))
        if v and v > 0:
            return v
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                offers = n.get("offers")
                for o in (offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []):
                    v = parse_price(str(o.get("price") or o.get("lowPrice") or ""))
                    if v and v > 0:
                        return v
                stack.extend(x for x in n.values() if isinstance(x, (dict, list)))
            elif isinstance(n, list):
                stack.extend(n)
    return None


def verify_store_prices(offers: list, limit: int = 24, budget: float = 9.0, cfg: dict | None = None, on_fix=None) -> int:
    """Correct prices from the product pages of VERIFY_STORES. Returns how many prices were changed."""
    # Price-comparison listings (StaticICE) are checked too: they often carry an old regular price while the shop's own
    # page already shows the sale price (this is how a $677 sale showed as $1,699).
    todo = [o for o in offers if o.source in ("store", "staticice")
            and (any(w in o.store.lower() for w in VERIFY_STORES) or any(w in o.url.lower() for w in VERIFY_STORES))][:limit]
    if not todo:
        return 0
    fixed, now = 0, time.time()
    use_b = browser_wanted(cfg)
    if use_b:
        budget = max(budget, 30.0)
    notes: list[str] = []

    def one(o):
        hit = _PAGE_PRICE_CACHE.get(o.url)
        if hit and now - hit[0] < 1800:
            return o, hit[1]
        v, why = None, ""
        try:
            v = page_price(fetch(o.url, timeout=(4, 6)))
            why = "no price tag on page" if v is None else ""
        except Exception as e:  # noqa: BLE001
            why = f"plain fetch failed ({type(e).__name__}: {str(e)[:50]})"
        if v is None and use_b:                          # the shop blocks scripts or builds the page late: use a real browser
            try:
                bhtml = BROWSER.render(o.url, 15)
                v = page_price(bhtml)
                tm = re.search(r"(?is)<title[^>]*>(.*?)</title>", bhtml or "")
                why += "; browser: " + ("ok" if v else f"no price tag on page (page title: {(tm.group(1).strip()[:60] if tm else 'none')}, {len(bhtml or '')} bytes)")
            except Exception as e:  # noqa: BLE001
                why += f"; browser failed ({str(e)[:50]})"
        if v is None:
            notes.append(f"{o.title[:50]} @ {o.price}: {why}")
        else:
            _PAGE_PRICE_CACHE[o.url] = (now, v)
            if len(_PAGE_PRICE_CACHE) > 600:
                for k in [k for k, h in list(_PAGE_PRICE_CACHE.items()) if now - h[0] >= 1800] or list(_PAGE_PRICE_CACHE)[:300]:
                    _PAGE_PRICE_CACHE.pop(k, None)
        return o, v

    ex = ThreadPoolExecutor(max_workers=8)
    futs = [ex.submit(one, o) for o in todo]
    try:
        pending, end = set(futs), time.time() + budget
        while pending and time.time() < end:            # corrections are handed over one by one as each page finishes
            finished, pending = wait(pending, timeout=max(0.05, end - time.time()), return_when=FIRST_COMPLETED)
            for fut in finished:
                o, v = fut.result()
                if v and abs(v - o.price) > 0.5:
                    old = o.price
                    o.price = v
                    if not o.was_price and v * 1.05 < old < v * 5:      # the figure we grabbed was probably the crossed-out price
                        o.was_price = old
                    elif o.was_price and o.was_price <= v:
                        o.was_price = None
                    fixed += 1
                    if on_fix:
                        try:
                            on_fix(o)
                        except Exception:  # noqa: BLE001
                            pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    try:                                                 # a small note you can send me if a price is still wrong
        (DATA_DIR / "price_check.log").write_text(
            time.strftime("%Y-%m-%d %H:%M:%S") + f"  checked {len(todo)} page(s), corrected {fixed}\n" + "\n".join(notes[:30]),
            encoding="utf-8")
    except OSError:
        pass
    return fixed


def _cancelled(cfg) -> bool:
    ev = (cfg or {}).get("_cancel")
    return bool(ev is not None and ev.is_set())


def _partial_rank(kw: str, results: list, cfg: dict | None) -> list:
    """A quick ranking of what has come back so far (no database writes, no price re-checks)."""
    words = blocked_words(cfg)
    raw = [o for _, offs, _ in results for o in offs]
    for o in raw:
        o.used = o.used or bool(USED_RE.search(o.title)) or o.store in USED_ONLY_STORES
    hid = hidden_url_set(db())
    visible = [o for o in raw if not is_hidden_offer(o, words) and o.url not in hid]
    ranked, _ = drop_junk_prices(rank_offers(kw, visible))
    return apply_ozb_discount(ranked)


def _find_pass(queries: list[tuple], stores: list[dict], cfg: dict | None = None, progress=None,
               deadline: float = 45.0, skip_dead: bool = True, partial=None) -> dict:
    """Scan every (search, store) pair at once on one shared pool. queries = [(key, keywords)].
    Returns {key: (offers ranked by relevance, Report)}. Slow stragglers are dropped after `deadline` seconds."""
    words, now = blocked_words(cfg), time.time()
    usable = [st for st in stores if not any(w in f"{st['name']} {st['search_url']}".lower() for w in words)]
    paused = [st for st in usable if skip_dead and (st.get("skip_until") or 0) > now
              and st["name"].lower() not in ALWAYS_TRY]
    live = [st for st in usable if st not in paused]
    results = {k: [] for k, _ in queries}
    late = {k: [] for k, _ in queries}
    picked = {k: select_stores(live, kw, cfg) for k, kw in queries}
    total = sum(len(v) for v in picked.values())
    ex = ThreadPoolExecutor(max_workers=max(1, min(POOL_WORKERS, total)))
    exb = ThreadPoolExecutor(max_workers=4)             # shops that need the hidden browser get their own lane, so they
    use_b = browser_wanted(cfg)                         # (Amazon, Big W, Officeworks...) start at once and don't wait behind every plain shop
    futs, bfuts, pfuts = {}, set(), set()
    for k, kw in queries:
        cats = detect_categories(kw)
        for st in sorted(picked[k], key=lambda s: (not _is_marketplace(s),) + _scan_order(s, cats)):
            browsery = use_b and st.get("use_browser")
            fut = (exb if browsery else ex).submit(_scan_one, dict(st), kw, cfg)
            futs[fut] = (k, st)
            if browsery:
                bfuts.add(fut)
                if _is_marketplace(st):
                    pfuts.add(fut)
    done, t0, cut, pending = 0, time.time(), deadline, set(futs)
    last_partial, sent = 0.0, None
    try:
        while pending:
            left = t0 + cut - time.time()
            if left <= 0 or _cancelled(cfg):
                break
            finished, pending = wait(pending, timeout=min(left, 0.4), return_when=FIRST_COMPLETED)
            for fut in finished:
                k, _ = futs[fut]
                results[k].append(fut.result())
                done += 1
                if progress:
                    progress(done, total)
            if partial and len(queries) == 1 and finished and pending and time.time() - last_partial >= 1.5:
                last_partial = time.time()                      # show the best results so far while the slow shops finish
                try:
                    k0, kw0 = queries[0]
                    early = _partial_rank(kw0, results[k0], cfg)
                    sig = [(o.url, o.price) for o in early[:40]]
                    if sum(1 for o in early if o.score >= 30) >= 3 and sig != sent:
                        sent = sig
                        partial(early, done, total)
                except Exception:  # noqa: BLE001
                    pass
            el = time.time() - t0
            if cut == deadline and total and done >= 0.85 * total and el >= 5 and (el >= 40 or not (pending & pfuts)) and (el >= 30 or not (pending & bfuts)):
                # most stores are in: don't wait long for the stragglers - but browser shops (Amazon...) are slow by
                # nature, so they get the full time unless it is already well over half a minute
                cut = min(deadline, el + max(3.0, el * 0.4))
    finally:
        for fut, (k, st) in futs.items():
            if not fut.done():
                fut.cancel()
                late[k].append(st)
        ex.shutdown(wait=False, cancel_futures=True)
        exb.shutdown(wait=False, cancel_futures=True)

    if _cancelled(cfg):                                       # stopped by a newer search: skip all the clean-up work
        return {k: ([], Report([])) for k, _ in queries}
    con, out, seen = db(), {}, {}
    for k, kw in queries:
        raw = [o for _, offs, _ in results[k] for o in offs]
        hid = hidden_url_set(con)
        for o in raw:
            o.used = o.used or bool(USED_RE.search(o.title)) or o.store in USED_ONLY_STORES
        visible, hidden_list = [], []
        for o in raw:                                    # keep what was left out, so "Show hidden listings" can bring it back
            if o.url in hid:
                hidden_list.append((o, "reported"))
            elif is_hidden_offer(o, words):
                hidden_list.append((o, "site"))
            else:
                visible.append(o)
        if (cfg or {}).get("defer_verify") != "1":      # the app checks prices after the results are on screen instead
            try:
                verify_store_prices(visible, cfg=cfg)
            except Exception:  # noqa: BLE001
                pass
        ranked0 = rank_offers(kw, visible)
        ranked, junk = drop_junk_prices(ranked0)
        kept_ids = {id(o) for o in ranked}
        hidden_list += [(o, "cheap") for o in ranked0 if id(o) not in kept_ids]
        ranked = apply_ozb_discount(ranked)
        try:
            record_seen(con, [o for o in ranked if o.source != "ozb" and o.score >= 30][:250])
            learn_vocab(con, [o for o in ranked if o.score >= ALERT_MIN_SCORE][:60])
        except Exception:  # noqa: BLE001
            pass
        report = Report({"id": s["id"], "name": s["name"],
                         "status": status_text(len(offs), err, bool(s.get("_browser_used"))),
                         "raw": len(offs), "err": err, "sample": [o.title for o in offs[:2]], "ms": s.get("_ms", 0)}
                        for s, offs, err in results[k])
        report.extend({"id": st["id"], "name": st["name"], "status": "Too slow - skipped this time",
                       "raw": 0, "err": "timeout"} for st in late[k])
        report.junk, report.hidden = junk, len(raw) - len(visible)
        seen_u, uniq = set(), []
        for o, why in hidden_list:
            if o.url not in seen_u and len(uniq) < 80:
                seen_u.add(o.url)
                uniq.append((o, why))
        report.hidden_offers = uniq
        report.ozb_titles = [f"${o.price:,.0f}  {o.title[:85]}" for o in raw if o.source == "ozb"][:60]
        report.words = {}
        for o in raw[:800]:                         # words the shops' own search found - used for "did you mean"
            for w in set(re.findall(r"[a-z]{4,}", o.title.lower())):
                report.words[w] = report.words.get(w, 0) + 1
        report.paused, report.timed_out = len(paused), len(late[k])
        report.paused_names = tuple(st['name'] for st in select_stores(paused, kw, cfg)) if paused else ()
        report.skipped = len(live) - len(picked[k])
        out[k] = (ranked, report)
        for s, offs, err in results[k]:
            agg = seen.setdefault(s["id"], [False, None, None])
            agg[0] = agg[0] or bool(offs)
            agg[1] = agg[1] or err
            agg[2] = status_text(len(offs), err, bool(s.get("_browser_used")))
    for sid, (ok, kind, status) in seen.items():
        record_health(con, sid, ok, kind)
        con.execute("UPDATE stores SET status=?, tested_at=? WHERE id=?", (status, time.time(), sid))
    con.commit()
    return out


def sample_resources() -> str:
    """One line about how much of the PC this program is holding: threads, Windows handles, GDI/USER objects, memory
    and helper (browser) processes. Written once a minute to resources.log so a slowdown can be traced."""
    parts = [time.strftime("%H:%M:%S"), f"threads={threading.active_count()}"]
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            h = k32.GetCurrentProcess()
            parts.append(f"gdi={u32.GetGuiResources(h, 0)} user={u32.GetGuiResources(h, 1)}")
            cnt = wintypes.DWORD()
            k32.GetProcessHandleCount(h, ctypes.byref(cnt))
            parts.append(f"handles={cnt.value}")

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pm = PMC()
            pm.cb = ctypes.sizeof(PMC)
            ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pm), pm.cb)
            parts.append(f"mem={pm.WorkingSetSize // 1048576}MB")

            class PE(ctypes.Structure):
                _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                            ("szExeFile", ctypes.c_wchar * 260)]
            snap = k32.CreateToolhelp32Snapshot(2, 0)
            kids, mine, n = {}, os.getpid(), 0
            pe = PE()
            pe.dwSize = ctypes.sizeof(PE)
            ok = k32.Process32FirstW(snap, ctypes.byref(pe))
            while ok:
                kids.setdefault(pe.th32ParentProcessID, []).append((pe.th32ProcessID, pe.szExeFile))
                ok = k32.Process32NextW(snap, ctypes.byref(pe))
            k32.CloseHandle(snap)
            stack, names = [mine], {}
            while stack:
                for pid, exe in kids.get(stack.pop(), []):
                    n += 1
                    names[exe.lower()] = names.get(exe.lower(), 0) + 1
                    stack.append(pid)
            parts.append(f"child_processes={n} " + ",".join(f"{k}x{v}" for k, v in sorted(names.items())[:5]))
        except Exception as e:  # noqa: BLE001
            parts.append(f"(sample failed: {type(e).__name__})")
    try:
        parts.append(f"browser={BROWSER.state}")
    except Exception:  # noqa: BLE001
        pass
    return "  ".join(parts)


def start_resource_log(every: float = 60.0) -> None:
    def run():
        path = DATA_DIR / "resources.log"
        while True:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()[-240:] if path.exists() else []
                lines.append(sample_resources())
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            time.sleep(every)
    threading.Thread(target=run, daemon=True).start()


LAST_SEARCH: dict = {"text": ""}


def _note_search(queries: list[tuple], out: dict) -> None:
    """Keep a plain-text account of the latest search (which shops answered, what was found and what was
    filtered) so "Why these results?" and the diagnostics can explain a thin or empty search."""
    try:
        if len(queries) != 1:
            return
        k, kw = queries[0]
        ranked, rep = out[k]
        dev = get_settings(db()).get("dev_mode", "0") == "1"          # source tags, timings and re-check notes are developer-only
        lines = [f"Search: {kw}", time.strftime("%Y-%m-%d %H:%M:%S") + (f"   (Deals engine v{ENGINE_VERSION})" if dev else ""), ""]
        raw = sum(r.get("raw", 0) for r in rep)
        rel = sum(1 for o in ranked if o.score >= 30)
        lines.append(f"{len(rep)} shops searched, {raw} listings came back, {len(ranked)} kept, {rel} closely match.")
        lines.append(f"Filtered out: {rep.junk} too cheap to be the product (cases, parts), {rep.hidden} from hidden sites.")
        lines.append(f"Not searched: {rep.skipped} (wrong category), {rep.paused} paused after repeated failures, "
                     f"{rep.timed_out} too slow." + ("  Widened to every shop." if rep.widened else ""))
        if getattr(rep, "paused_names", ()):
            lines.append("Paused shops that WOULD have been searched: " + ", ".join(rep.paused_names))
        if rep.second_tried:
            lines.append(f"Second pass: {rep.second_tried} slow shops tried again after the first results, {rep.second_added} new listings added.")
        lines += ["", "SHOPS (listings returned)"]
        for r in sorted(rep, key=lambda r: (-r.get("raw", 0), r["name"])):
            ms = r.get("ms") or 0
            lines.append(f"- {r['name']}: {r.get('raw', 0)}  {r.get('status', '')}" + (f"  [{ms / 1000:.1f}s]" if ms and dev else ""))
        if rel < 3:                                    # thin result: show what the shops actually sent back
            lines += ["", "WHAT THE SHOPS SENT BACK (first two listings of each)"]
            for r in sorted(rep, key=lambda r: -r.get("raw", 0))[:25]:
                for t in r.get("sample") or []:
                    lines.append(f"- {r['name']}: {t[:90]}")
        lines += ["", "TOP RESULTS (score, price, shop" + (" [where it came from]" if dev else "") + ", title, crossed-out price)"]
        for o in ranked[:25]:
            src = {"store": "shop's own search", "staticice": "StaticICE", "ozb": "OzBargain"}.get(o.source, o.source)
            was = f"  was ${o.was_price:,.2f}" if o.was_price else ""
            lines.append(f"- {o.score:>3}  ${o.price:,.2f}  {o.store}{f' [{src}]' if dev else ''}  {o.title[:80]}{was}")
        if dev:
            if AMAZON_STATS.get("cards"):
                a = AMAZON_STATS
                lines += ["", f"AMAZON: {a['cards']} result cards, {a['fromprice']} priced from a 'from $' line, {a['noprice']} skipped (no price shown)"]
                lines += [f"- skipped: {t}" for t in a.get("titles_noprice", [])]
                lines += ["", "EVERY AMAZON CARD, IN PAGE ORDER (ASIN, price, title)"] + [f"- {t}" for t in a.get("all", [])]
            if getattr(rep, "ozb_titles", None):
                lines += ["", f"OZBARGAIN FEED ITEMS ({len(rep.ozb_titles)} returned)"] + [f"- {t}" for t in rep.ozb_titles[:40]]
            try:
                chk = (DATA_DIR / "price_check.log").read_text(encoding="utf-8").strip()
                if chk:
                    lines += ["", "PRICE RE-CHECK AGAINST SHOP PAGES (JB Hi-Fi, Bing Lee, Betta)", chk[:1500]]
            except OSError:
                pass
        LAST_SEARCH["text"] = "\n".join(lines)
    except Exception:  # noqa: BLE001
        pass


WIDEN_BELOW = 3     # fewer relevant listings than this -> also try the shops that were skipped by category


def find_offers_many(queries: list[tuple], stores: list[dict], cfg: dict | None = None, progress=None,
                     deadline: float = 45.0, skip_dead: bool = True, partial=None) -> dict:
    """One scan on the shops that fit the product. A search that finds almost nothing is automatically
    widened to the remaining shops (only for that search), so unusual products are still found."""
    out = _find_pass(queries, stores, cfg, progress, deadline, skip_dead, partial)
    if _cancelled(cfg):
        return out
    if (cfg or {}).get("scope", "smart") == "all" or (cfg or {}).get("widen", "1") == "0":
        _note_search(queries, out)
        return out
    thin = [(k, kw) for k, kw in queries
            if k in out and out[k][1].skipped > 0 and sum(1 for o in out[k][0] if o.score >= 30) < WIDEN_BELOW]
    for k, kw in thin:
        try:
            tried = {r["id"] for r in out[k][1]}
            rest = [st for st in stores if st["id"] not in tried and not (st.get("skip_until") or 0) > time.time()]
            if not rest:
                continue
            ranked2, rep2 = _find_pass([(k, kw)], rest, dict(cfg or {}, scope="all"), None, min(deadline, 40.0), skip_dead)[k]
            ranked, rep = out[k]
            have = {o.url for o in ranked}
            merged = ranked + [o for o in ranked2 if o.url not in have]
            merged.sort(key=lambda o: -o.score)
            rep.extend(rep2)
            rep.junk += rep2.junk
            rep.hidden += rep2.hidden
            rep.hidden_offers = list(rep.hidden_offers) + [(o, w) for o, w in rep2.hidden_offers
                                                           if o.url not in {x.url for x, _ in rep.hidden_offers}]
            rep.timed_out += rep2.timed_out
            rep.skipped = 0
            rep.widened = True
            for w, n in rep2.words.items():
                rep.words[w] = rep.words.get(w, 0) + n
            out[k] = (merged, rep)
        except Exception:  # noqa: BLE001
            pass
    _note_search(queries, out)
    return out


SECOND_PASS_MAX = 18
BREADTH = {"general": 0, "all": 0, "office": 1, "home": 1, "diy": 1, "tech": 2,
           "sports": 3, "outdoor": 3, "gaming": 3, "garden": 3}          # anything else (fashion, beauty, baby, books...) = 4


def _breadth(st: dict) -> tuple:
    """How wide a range a shop sells: used to decide who gets a second go first when the search names no kind of product."""
    cs = (st.get("cats") or "all").split()
    return (min((BREADTH.get(c, 4) for c in cs), default=0), -len(cs))


def second_pass(keywords: str, stores: list[dict], offers: list, report, cfg: dict | None = None, deadline: float = 40.0):
    """After the first results are on screen: give the shops that were 'too slow' another go, on their own (so nothing
    else is competing for the hidden browser). Returns (merged offers, updated report, number of new listings), or None."""
    late_ids = {r["id"] for r in report if r.get("err") == "timeout"}
    todo = [st for st in stores if st["id"] in late_ids]
    if not todo or _cancelled(cfg):
        return None
    cats = detect_categories(keywords)
    todo.sort(key=lambda s: (not _is_marketplace(s), _scan_order(s, cats)[0]) + _breadth(s) + (s.get("name", ""),))
    todo = todo[:SECOND_PASS_MAX]
    c2 = dict(cfg or {}, defer_verify="1", scope="all")
    ranked2, rep2 = _find_pass([("q", keywords)], todo, c2, None, deadline, False)["q"]
    if _cancelled(cfg):
        return None
    have = {o.url for o in offers}
    new = [o for o in ranked2 if o.url not in have]
    merged = sorted(list(offers) + new, key=lambda o: (-o.score, o.price))
    tried = {st["id"] for st in todo}
    rep = Report([r for r in report if r["id"] not in tried] + list(rep2))
    for a in ("paused", "paused_names", "skipped", "widened", "words", "ozb_titles"):
        setattr(rep, a, getattr(report, a, getattr(Report, a)))
    rep.junk, rep.hidden = report.junk + rep2.junk, report.hidden + rep2.hidden
    seen_h = {o.url for o, _ in report.hidden_offers}
    rep.hidden_offers = list(report.hidden_offers) + [(o, w) for o, w in rep2.hidden_offers if o.url not in seen_h]
    rep.timed_out = (report.timed_out - len(tried)) + rep2.timed_out
    rep.second_tried, rep.second_added = len(tried), len(new)
    try:
        _note_search([("q", keywords)], {"q": (merged, rep)})
    except Exception:  # noqa: BLE001
        pass
    return merged, rep, len(new)


def find_offers(keywords: str, stores: list[dict], cfg: dict | None = None, workers: int | None = None,
                progress=None, deadline: float = 45.0, partial=None):
    """Search every store in parallel. Returns (offers ranked by relevance, per-store report).
    `partial(offers, done, total)` is called with the best results so far while slower shops are still answering."""
    return find_offers_many([("q", keywords)], stores, cfg, progress, deadline, partial=partial)["q"]


SAMPLE_QUERY = {"tech": "laptop", "gaming": "controller", "home": "kettle", "diy": "drill", "garden": "mower",
                "fashion": "shoes", "sports": "running shoes", "outdoor": "tent", "baby": "stroller", "toys": "lego",
                "pets": "dog food", "beauty": "shampoo", "fragrance": "perfume", "luxury": "handbag", "auto": "wiper blades", "books": "cookbook",
                "grocery": "coffee", "office": "pen", "music": "guitar"}


def sample_query(store: dict) -> str:
    """A search the shop is sure to have results for, so a test says something about the shop, not the query."""
    for c in (store.get("cats") or "").split():
        if c in SAMPLE_QUERY:
            return SAMPLE_QUERY[c]
    return "laptop"


_STEP = threading.local()


def _step(text: str) -> None:
    """Tell whoever is watching (the Sources test card) what is happening right now."""
    cb = getattr(_STEP, "cb", None)
    if cb:
        try:
            cb(text)
        except Exception:  # noqa: BLE001
            pass


def test_store(store: dict, query: str | None = None, cfg: dict | None = None, step=None) -> tuple[str, bool]:
    query = query or sample_query(store)
    _STEP.cb = step
    _step(f"Searching for \u201c{query}\u201d")
    try:
        n = len(scrape_store(store, query, cfg, query))
        return status_text(n, None, bool(store.get("_browser_used"))), n > 0
    except FetchError as e:
        return status_text(0, e.kind), False
    except Exception:  # noqa: BLE001
        return status_text(0, "error"), False
    finally:
        _STEP.cb = None


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
def notify(s: dict, subject: str, body: str, url: str | None, log=print):
    if s.get("ntfy"):
        try:
            h = {"Title": subject.encode("utf-8"), "Priority": "high", "Tags": "moneybag"}
            if url:
                h["Click"] = url
            requests.post(f"https://ntfy.sh/{s['ntfy']}", data=body.encode("utf-8"), headers=h, timeout=15).raise_for_status()
        except requests.RequestException as e:
            log(f"ntfy failed: {e}")
    if s.get("discord"):
        try:
            requests.post(s["discord"], json={"content": f"**{subject}**\n{body}"}, timeout=15).raise_for_status()
        except requests.RequestException as e:
            log(f"Discord failed: {e}")
    if s.get("tg_token") and s.get("tg_chat"):
        try:
            requests.post(f"https://api.telegram.org/bot{s['tg_token']}/sendMessage",
                          json={"chat_id": s["tg_chat"], "text": f"{subject}\n{body}"}, timeout=15).raise_for_status()
        except requests.RequestException as e:
            log(f"Telegram failed: {e}")
    if s.get("email_host") and s.get("email_to"):
        try:
            msg = EmailMessage()
            msg["Subject"], msg["From"], msg["To"] = subject, s.get("email_from") or s["email_user"], s["email_to"]
            msg.set_content(body)
            with smtplib.SMTP(s["email_host"], int(float(s.get("email_port") or 587)), timeout=20) as srv:
                srv.starttls()
                srv.login(s["email_user"], s["email_pass"])
                srv.send_message(msg)
        except Exception as e:  # noqa: BLE001
            log(f"Email failed: {e}")


def expiry_text(ts: float, now: float | None = None) -> str:
    """'ends Sat 23 Nov 18:00 (in 2d 4h)'"""
    left = ts - (now or time.time())
    when = time.strftime("%a %d %b %H:%M", time.localtime(ts))
    if left <= 0:
        return f"ended {when}"
    d, rem = divmod(int(left), 86400)
    h, m = rem // 3600, (rem % 3600) // 60
    span = f"{d}d {h}h" if d else (f"{h}h {m}m" if h else f"{m}m")
    return f"ends {when} (in {span})"


def cut_text(sym: str, old: float, new: float) -> str:
    """'-$120.99, -30%' for a price falling from old to new."""
    d = old - new
    return f"-{money(sym, d)}, -{100 * d / old:.0f}%"


def evaluate(con, item, offer: Offer, sym: str = "$") -> list[str]:
    """Reasons this offer deserves an alert (empty = no alert)."""
    min_drop = (item["min_drop_pct"] or 10) / 100
    if offer.source == "ozb":                          # community-posted deal (already filtered to discounted ones)
        base = offer.was_price or offer.ref_price
        marked = bool(base and (base - offer.price) / base >= min_drop)
        on_target = item["max_price"] is not None and offer.price <= item["max_price"]
        if item["max_price"] is not None and not on_target:
            return []
        if not (on_target or marked):
            return []
        bits = [f"OzBargain deal ({offer.votes:+d} votes)"]
        if on_target:
            bits.append(f"at/below your {money(sym, item['max_price'])} target")
        if marked and offer.was_price:
            bits.append(f"marked down from {money(sym, offer.was_price)} ({cut_text(sym, offer.was_price, offer.price)})")
        elif marked:
            bits.append(f"{100 * (base - offer.price) / base:.0f}% below other shops (typically {money(sym, base)})")
        if offer.expires:
            bits.append(expiry_text(offer.expires))
        return bits
    prev = con.execute("SELECT price FROM prices WHERE item_id=? AND url=? ORDER BY seen_at DESC LIMIT 1",
                       (item["id"], offer.url)).fetchone()
    on_sale = bool(offer.was_price and offer.was_price > offer.price
                   and (offer.was_price - offer.price) / offer.was_price >= min_drop)
    dropped = bool(prev and prev["price"] > offer.price
                   and (prev["price"] - offer.price) / prev["price"] >= min_drop)
    reasons = []
    if item["max_price"] is not None:
        if offer.price <= item["max_price"]:
            reasons.append(f"at/below your {money(sym, item['max_price'])} target")
            if on_sale:
                reasons.append(f"marked down from {money(sym, offer.was_price)} ({cut_text(sym, offer.was_price, offer.price)})")
            if dropped:
                reasons.append(f"dropped from {money(sym, prev['price'])} ({cut_text(sym, prev['price'], offer.price)})")
    else:
        if on_sale:
            reasons.append(f"marked down from {money(sym, offer.was_price)} ({cut_text(sym, offer.was_price, offer.price)})")
        if dropped:
            reasons.append(f"dropped from {money(sym, prev['price'])} ({cut_text(sym, prev['price'], offer.price)})")
    return reasons


def regular_price(con, item_id: int, days: int = 180) -> tuple[float, int] | None:
    """(usual price when NOT on sale, how many prices it's based on). Uses the shops' own 'was' prices and the
    prices of listings that weren't discounted - not the sale prices - and takes the middle value so one odd
    listing can't skew it. None until there are at least 3 such prices."""
    vals = sorted(r[0] for r in con.execute(
        "SELECT reg FROM prices WHERE item_id=? AND reg IS NOT NULL AND seen_at>?", (item_id, time.time() - days * 86400)))
    if len(vals) < 3:
        return None
    return vals[len(vals) // 2], len(vals)


def reset_history(con, item_id: int) -> list[tuple]:
    """Clear an item's price history (the graph). Returns the removed rows so the caller can offer Undo."""
    rows = [tuple(r) for r in con.execute(
        "SELECT item_id,store,url,title,price,seen_at,reg FROM prices WHERE item_id=?", (item_id,))]
    con.execute("DELETE FROM prices WHERE item_id=?", (item_id,))
    con.execute("UPDATE watchlist SET best_price=NULL, best_store=NULL, best_title=NULL, best_url=NULL WHERE id=?", (item_id,))
    con.commit()
    return rows


def restore_history(con, rows: list[tuple]):
    con.executemany("INSERT INTO prices(item_id,store,url,title,price,seen_at,reg) VALUES(?,?,?,?,?,?,?)", rows)
    con.commit()


def price_history(con, item_id: int) -> list[dict]:
    """Cheapest good match at each check, oldest first: [{t, price, store, url, title}]."""
    rows = con.execute("SELECT seen_at, price, store, url, title FROM prices WHERE item_id=? "
                       "ORDER BY seen_at, price", (item_id,)).fetchall()
    out, last = [], None
    for r in rows:
        if r["seen_at"] != last:
            out.append({"t": r["seen_at"], "price": r["price"], "store": r["store"],
                        "url": r["url"], "title": r["title"]})
            last = r["seen_at"]
    return out


def last_prices(con, urls) -> dict:
    """Most recent price we recorded for each URL (from earlier watchlist checks)."""
    urls, out = list(urls), {}
    for i in range(0, len(urls), 500):
        chunk = urls[i:i + 500]
        q = "SELECT url, price FROM prices WHERE url IN (%s) ORDER BY seen_at" % ",".join("?" * len(chunk))
        for r in con.execute(q, chunk):
            out[r["url"]] = r["price"]
    return out


def already_alerted(con, item_id, url, price) -> bool:
    row = con.execute("SELECT price, sent_at FROM alerts WHERE item_id=? AND url=? "
                      "ORDER BY sent_at DESC LIMIT 1", (item_id, url)).fetchone()
    return bool(row and price >= row["price"] * 0.999 and time.time() - row["sent_at"] < 7 * 86400)


LOW_RATIO = 0.3     # a listing under this share of the item's usual price, with no real 'was' price, is not the same product


def usual_ref(con, item_id: int) -> float | None:
    """What this watchlist item normally costs: the shops' usual price, or failing that the middle of its own history."""
    reg = regular_price(con, item_id)
    if reg:
        return reg[0]
    hist = sorted(h["price"] for h in price_history(con, item_id))
    return hist[len(hist) // 2] if len(hist) >= 3 else None


def implausibly_low(o: Offer, ref: float | None) -> bool:
    """A $35 listing for a $1,100 watch is a strap or a film, not a 97% sale. A real markdown shows a crossed-out price."""
    return bool(ref) and o.price < LOW_RATIO * ref and not (o.was_price and o.was_price >= 0.6 * ref)


def run_check(log=print, on_alert=None, progress=None, only_id: int | None = None) -> int:
    """Check every watchlist item (or just `only_id`, even if paused) across all active stores. Returns alerts sent."""
    con = db()
    s = get_settings(con)
    if only_id is not None:
        items = con.execute("SELECT * FROM watchlist WHERE id=?", (only_id,)).fetchall()
    else:
        items = con.execute("SELECT * FROM watchlist WHERE COALESCE(paused,0)=0").fetchall()
    stores = active_stores(con, s["region"])
    saved = con.execute("SELECT * FROM saved_searches").fetchall() if only_id is None else []
    if not items and not saved:
        log("Your watchlist is empty - add something first.")
        return 0
    if not stores:
        log("No stores are enabled. Pick a region or switch stores on.")
        return 0
    sym, now, sent = s["currency"], time.time(), 0
    held = hold_alerts(s)
    log(f"Checking {len(items)} item(s) across {len(stores)} sources" + (" (alerts held until your summary / quiet hours end)" if held else ""))
    results = find_offers_many([(it["id"], it["keywords"]) for it in items] + [(f"s{x['id']}", x["query"]) for x in saved],
                               stores, s, progress=progress, deadline=75.0)

    for item in items:
        ranked, report = results[item["id"]]
        skip = [w.strip().lower() for w in (item["ignore_stores"] or "").split(",") if w.strip()]
        offers = sorted((o for o in ranked if o.score >= ALERT_MIN_SCORE and not o.accessory and not o.used
                         and not any(w in o.store.lower() for w in skip)), key=lambda o: o.price)
        ref = usual_ref(con, item["id"])
        if ref:
            low = [o for o in offers if implausibly_low(o, ref)]
            if low:
                offers = [o for o in offers if o not in low]
                log(f"{item['keywords']}: ignored {len(low)} listing(s) far below the usual price (probably accessories)")
            try:                                          # and clear any such rows an earlier check already saved
                con.execute("DELETE FROM prices WHERE item_id=? AND price<? AND (reg IS NULL OR reg<?)",
                            (item["id"], LOW_RATIO * ref, 0.6 * ref))
            except Exception:  # noqa: BLE001
                pass
        only_at = (item["stock_store"] or "").strip().lower()
        stock_now = [o for o in offers if not o.oos and (item["max_price"] is None or o.price <= item["max_price"])
                     and (not only_at or only_at in o.store.lower())]
        if item["want_stock"] and not item["had_stock"] and stock_now:        # it was all sold out before; now it's not
            o = stock_now[0]
            if not already_alerted(con, item["id"], o.url, o.price):
                subject = f"Back in stock: {o.title[:60]} - {money(sym, o.price)} at {o.store}"
                if not held:
                    notify(s, subject, f"{o.title}\n{money(sym, o.price)}\n{o.url}", o.url, log)
                con.execute("INSERT INTO alerts(item_id,keywords,title,store,url,price,reasons,sent_at,notified) VALUES(?,?,?,?,?,?,?,?,?)",
                            (item["id"], item["keywords"], o.title, o.store, o.url, o.price, "back in stock", now, 0 if held else 1))
                sent += 1
                if on_alert and not held:
                    on_alert({"keywords": item["keywords"], "title": o.title, "store": o.store, "price": o.price,
                              "url": o.url, "reasons": "back in stock"})
        con.execute("UPDATE watchlist SET had_stock=? WHERE id=?", (1 if stock_now else 0, item["id"]))
        offers = [o for o in offers if not o.oos]
        ok = sum(1 for r in report if r["raw"] > 0)
        log(f"{item['keywords']}: {ok} of {len(report)} sources returned products - {len(offers)} matching"
            + (f" ({report.paused} paused, {report.timed_out} too slow)" if report.paused or report.timed_out else ""))
        for o in offers:
            reasons = evaluate(con, item, o, sym)
            if reasons and not already_alerted(con, item["id"], o.url, o.price):
                subject = f"Deal: {o.title[:60]} - {money(sym, o.price)} at {o.store}"
                body = f"{o.title}\n{money(sym, o.price)} ({'; '.join(reasons)})\n{o.url}"
                if not held:
                    notify(s, subject, body, o.url, log)
                con.execute("INSERT INTO alerts(item_id,keywords,title,store,url,price,reasons,sent_at,notified) "
                            "VALUES(?,?,?,?,?,?,?,?,?)",
                            (item["id"], item["keywords"], o.title, o.store, o.url, o.price,
                             "; ".join(reasons), now, 0 if held else 1))
                sent += 1
                log(f"DEAL: {subject}")
                if on_alert and not held:
                    on_alert({"keywords": item["keywords"], "title": o.title, "store": o.store,
                              "price": o.price, "url": o.url, "reasons": "; ".join(reasons)})
            if o.source != "ozb":                      # community posts never go into the retailer price history
                pct_, kind_ = deal_pct(o)
                reg = o.was_price if kind_ == "markdown" else (o.price if kind_ is None else None)
                con.execute("INSERT INTO prices(item_id,store,url,title,price,seen_at,reg) VALUES(?,?,?,?,?,?,?)",
                            (item["id"], o.store, o.url, o.title, o.price, now, reg))
        best = offers[0] if offers else None
        con.execute("UPDATE watchlist SET best_price=?, best_store=?, best_title=?, best_url=?, checked_at=? "
                    "WHERE id=?", (best.price if best else None, best.store if best else None,
                                   best.title if best else None, best.url if best else None, now, item["id"]))
        con.commit()
    for ss in saved:
        try:
            ranked, _rep = results[f"s{ss['id']}"]
            for o, why in saved_matches(con, ss, ranked, sym):
                subject = f"{ss['query']}: {o.title[:50]} - {money(sym, o.price)} at {o.store}"
                if not held:
                    notify(s, subject, f"{o.title}\n{money(sym, o.price)} ({why})\n{o.url}", o.url, log)
                con.execute("INSERT INTO alerts(item_id,keywords,title,store,url,price,reasons,sent_at,notified) "
                            "VALUES(?,?,?,?,?,?,?,?,?)", (-ss["id"], ss["query"], o.title, o.store, o.url, o.price, why,
                                                         now, 0 if held else 1))
                sent += 1
                if on_alert and not held:
                    on_alert({"keywords": ss["query"], "title": o.title, "store": o.store, "price": o.price,
                              "url": o.url, "reasons": why})
            con.commit()
        except Exception as e:  # noqa: BLE001
            log(f"saved search '{ss['query']}' failed: {e}")
    try:
        send_pending(con, s, log)
    except Exception as e:  # noqa: BLE001
        log(f"summary failed: {e}")
    return sent


# --------------------------------------------------------------------------- #
# Saved searches, buy hints, price-match text, reports, import, updates
# --------------------------------------------------------------------------- #
def review_rating(info: dict | None) -> float | None:
    """Plain star rating (out of 5) from a review-info dict, or None."""
    if not info:
        return None
    if info.get("rating"):
        return float(info["rating"])
    if info.get("pr"):
        return float(info["pr"][0])
    return None


def saved_matches(con, ss, ranked: list[Offer], sym: str = "$", limit: int = 3) -> list[tuple[Offer, str]]:
    """Offers that fit a saved search (price cap, real discount, minimum stars) and haven't been alerted before."""
    cands = [o for o in ranked if o.score >= ALERT_MIN_SCORE and not o.accessory and not o.used and not o.oos]
    if ss["max_price"]:
        cands = [o for o in cands if o.price <= ss["max_price"]]
    if ss["deals_only"]:
        cands = [o for o in cands if deal_pct(o)[1]]
    out = []
    for o in sorted(cands, key=lambda o: o.price)[:10]:
        if already_alerted(con, -ss["id"], o.url, o.price):
            continue
        why = [f"saved search '{ss['query']}'"]
        pct, kind = deal_pct(o)
        if kind and pct:
            why.append(f"{pct:.0f}% off")
        if ss["min_rating"]:
            r = review_rating(review_info_for(o))
            if r is None or r < ss["min_rating"]:
                continue
            why.append(f"\u2605 {r:.1f}")
        out.append((o, "; ".join(why)))
        if len(out) >= limit:
            break
    return out


def next_sale_event(now: float | None = None, within: int = 45) -> tuple[str, int] | None:
    """(name, days away) of the next big Australian sale event within `within` days."""
    t = time.localtime(now or time.time())
    today = datetime(t.tm_year, t.tm_mon, t.tm_mday)
    found = []
    for yr in (t.tm_year, t.tm_year + 1):
        d = datetime(yr, 11, 1)
        fridays = [d.replace(day=n) for n in range(1, 31) if d.replace(day=n).weekday() == 4]
        bf = fridays[3]                                   # fourth Friday of November
        found += [("Black Friday", bf), ("Cyber Monday", bf + timedelta(days=3)),
                  ("Boxing Day sales", datetime(yr, 12, 26)), ("End of financial year sales", datetime(yr, 6, 15)),
                  ("Click Frenzy", datetime(yr, 11, 11))]
    best = None
    for name, day in found:
        n = (day - today).days
        if 0 < n <= within and (best is None or n < best[1]):
            best = (name, n)
    return best


def buy_hint(price: float | None, reg: float | None, hist_prices: list[float], now: float | None = None) -> tuple[str, str]:
    """('good' | 'wait' | 'ok', one-line advice) from the price against its history and the sale calendar."""
    if not price:
        return "ok", ""
    ev = next_sale_event(now)
    if len(hist_prices) >= 5 and price <= min(hist_prices) * 1.005 and max(hist_prices) > price * 1.03:
        return "good", "Lowest price we've tracked - a good time to buy"
    if reg and price <= reg * 0.85:
        return "good", f"{100 * (reg - price) / reg:.0f}% below its usual price - a good time to buy"
    if ev and (not reg or price >= reg * 0.95):
        return "wait", f"{ev[0]} is {ev[1]} day{'s' if ev[1] != 1 else ''} away - it may drop further, so consider waiting"
    if reg and price > reg * 1.05:
        return "wait", f"{100 * (price - reg) / reg:.0f}% above its usual price - worth waiting"
    return "ok", "Around its usual price"


_DIAG_HIDE = re.compile(r"pass|token|discord|tg_|email|ntfy|smtp|webhook|chat|user|topic|url|key|secret|"
                        r"recent|viewed|foryou|daily_cat|folder|search|seen|geometry", re.I)


def build_diagnostics(data_dir: str | os.PathLike | None = None) -> tuple[str, str]:
    """Collect what is needed to work out why something is failing and zip it: versions, settings (no passwords,
    addresses or alert details), every source's status, and the end of the log files. Never includes the watchlist
    or search history. Returns (zip path, short text summary)."""
    import zipfile
    import platform
    data_dir = Path(data_dir or DB_PATH.parent)
    con = db()
    cfg = get_settings(con)
    safe = {k: v for k, v in sorted(cfg.items()) if not _DIAG_HIDE.search(k)}
    stores = con.execute("SELECT name, enabled, status, fail_streak, skip_until, tested_at, custom, search_url "
                         "FROM stores ORDER BY name").fetchall()
    now = time.time()
    lines = [f"Deals diagnostics  -  {time.strftime('%Y-%m-%d %H:%M')}",
             f"version {ENGINE_VERSION}  frozen={FROZEN}  python {platform.python_version()}  {platform.platform()}",
             f"browser: {browser_status(cfg)}", ""]
    on = sum(1 for r in stores if r["enabled"])
    bad = [r for r in stores if r["enabled"] and status_mark(r["status"] or "") == "x"]
    lines.append(f"sources: {len(stores)} total, {on} on, {len(bad)} of the enabled ones failing")
    lines.append("")
    lines.append("FAILING / PAUSED SOURCES")
    for r in stores:
        paused = (r["skip_until"] or 0) > now
        if r in bad or paused:
            lines.append(f"- {r['name']}{' (custom)' if r['custom'] else ''}: {r['status']}  streak={r['fail_streak']}"
                         f"{'  PAUSED' if paused else ''}  {r['search_url']}")
    lines += ["", "SETTINGS (private ones left out)"] + [f"{k} = {v}" for k, v in safe.items()]
    summary = "\n".join(lines)

    def tail(name, n=250):
        p = data_dir / name
        try:
            return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
        except OSError:
            return "(none)"
    out = data_dir / f"diagnostics-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("summary.txt", summary)
        z.writestr("all_sources.txt", "\n".join(
            f"{r['name']}\t{'on' if r['enabled'] else 'off'}\t{r['status']}\t{r['search_url']}" for r in stores))
        try:
            z.writestr("price_audit.txt", price_audit(cfg))
        except Exception as ex:  # noqa: BLE001
            z.writestr("price_audit.txt", f"(audit failed: {ex})")
        try:
            z.writestr("resources_now.txt", sample_resources())
        except Exception:  # noqa: BLE001
            pass
        z.writestr("last_search.txt", LAST_SEARCH["text"] or "(no search yet this session)")
        for name in ("deals_error.log", "price_check.log", "image_check.log", "resources.log"):
            z.writestr(name, tail(name))
        try:                                                   # a few raw OzBargain items, to check which fields the feed offers
            raw = fetch(OZB_BASE + "/deals/feed", timeout=(5, 8), accept="application/rss+xml,application/xml,text/xml,*/*", ua=OZB_UA)
            items = re.findall(r"(?s)<item>.*?</item>", raw)[:4]
            z.writestr("ozbargain_feed_sample.xml", "\n\n".join(items) or raw[:4000])
        except Exception as ex:  # noqa: BLE001
            z.writestr("ozbargain_feed_sample.xml", f"(could not fetch: {ex})")
    for old in sorted(data_dir.glob("diagnostics-*.zip"))[:-5]:       # keep only the newest few
        try:
            old.unlink()
        except OSError:
            pass
    return str(out), summary


def price_pattern(hist: list[dict]) -> dict:
    """What a product's own history says: its typical price, how often it drops and when it last did."""
    pts = [(h["t"], h["price"]) for h in hist if h.get("price")]
    out = {"n": len(pts), "span": 0.0, "drops": []}
    if len(pts) < 2:
        return out
    out["span"] = (pts[-1][0] - pts[0][0]) / 86400
    for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
        if p1 <= p0 * 0.95:
            out["drops"].append((t1, 100 * (p0 - p1) / p0))
    return out


def buy_advice(price: float | None, reg: float | None, hist: list[dict], now: float | None = None,
               sym: str = "$") -> dict | None:
    """Wait-or-buy advice from the price history and the sale calendar.
    {'verdict': 'buy'|'wait'|'fair'|'learning', 'headline', 'detail': [lines], 'basis'}"""
    if not price:
        return None
    now = now or time.time()
    pat = price_pattern(hist)
    prices = sorted(h["price"] for h in hist if h.get("price"))
    n, span = pat["n"], pat["span"]
    basis = f"based on {n} check{'s' if n != 1 else ''} over {span:.0f} day{'s' if round(span) != 1 else ''}"
    if n < 3 or span < 5:
        return {"verdict": "learning", "headline": "Still learning this price",
                "detail": ["Needs a few more checks over several days before it can say buy or wait."], "basis": basis}
    lo, hi, med = prices[0], prices[-1], prices[len(prices) // 2]
    ev = next_sale_event(now)
    detail, drops = [], pat["drops"]
    if len(drops) >= 2:
        gaps = sorted((b[0] - a[0]) / 86400 for a, b in zip(drops, drops[1:]))
        gap = gaps[len(gaps) // 2]
        avg = sum(d[1] for d in drops) / len(drops)
        ago = (now - drops[-1][0]) / 86400
        line = f"It tends to drop about {avg:.0f}% every {gap:.0f} days (last drop {ago:.0f} days ago)"
        if gap > ago + 2:
            line += f" - the next dip may be around {gap - ago:.0f} days away"
        detail.append(line)
    if price <= lo * 1.01 and hi > price * 1.03:
        return {"verdict": "buy", "headline": "Buy now",
                "detail": [f"The lowest price tracked so far (it has been up to {money(sym, hi)})"] + detail, "basis": basis}
    if reg and price <= reg * 0.85:
        return {"verdict": "buy", "headline": "Buy now",
                "detail": [f"{100 * (reg - price) / reg:.0f}% below its usual price"] + detail, "basis": basis}
    if ev and price >= med * 0.97:
        return {"verdict": "wait", "headline": "Wait",
                "detail": [f"{ev[0]} is {ev[1]} day{'s' if ev[1] != 1 else ''} away and it may drop further"] + detail,
                "basis": basis}
    if price > med * 1.05:
        return {"verdict": "wait", "headline": "Wait",
                "detail": [f"{100 * (price - med) / med:.0f}% above its typical price ({money(sym, med)}); it has been as low as {money(sym, lo)}"]
                + detail, "basis": basis}
    return {"verdict": "fair", "headline": "Fair price",
            "detail": [f"Close to its typical price ({money(sym, med)})"] + detail, "basis": basis}


def price_match_text(title: str, cheaper: Offer, my_store: str, sym: str = "$") -> str:
    """A short message to send a shop asking them to match a cheaper price."""
    return (f"Hi {my_store} team,\n\nI'd like to buy the {title} from you, but I've found it for "
            f"{money(sym, cheaper.price)} at {cheaper.store}:\n{cheaper.url}\n\n"
            f"Could you please match that price? Happy to complete my order straight away if you can.\n\nThanks!")


def import_items(con, lines: list[str], cfg: dict | None = None, log=print) -> tuple[int, int, list[str]]:
    """Add many watchlist items at once. A line is a product name or a product link. Returns (added, already_there, failed)."""
    added = dup = 0
    failed: list[str] = []
    have = {norm(r["keywords"]) for r in con.execute("SELECT keywords FROM watchlist")}
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            kw = product_from_url(line, cfg)["query"] if is_url(line) else line
        except Exception as e:  # noqa: BLE001
            failed.append(f"{line[:60]} ({e})")
            continue
        if not parse_keywords(kw)[0]:
            failed.append(line[:60])
        elif norm(kw) in have:
            dup += 1
        else:
            con.execute("INSERT INTO watchlist(keywords) VALUES(?)", (kw,))
            have.add(norm(kw))
            added += 1
    con.commit()
    return added, dup, failed


def watch_report_html(con, sym: str = "$") -> str:
    rows = con.execute("SELECT * FROM watchlist ORDER BY COALESCE(folder,''), id").fetchall()
    out = ["<!doctype html><meta charset='utf-8'><title>Deals - Watchlist report</title>"
           "<style>body{font:14px system-ui;margin:32px;color:#111}table{border-collapse:collapse;width:100%}"
           "td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}th{font-size:12px;color:#666}"
           ".g{color:#047857;font-weight:600}</style>",
           f"<h1>Watchlist report</h1><p>{time.strftime('%d %b %Y %H:%M')}</p>",
           "<table><tr><th>Item</th><th>Best now</th><th>Store</th><th>Target</th><th>Usual price</th><th>Lowest tracked</th><th>Checks</th></tr>"]
    for r in rows:
        hist = price_history(con, r["id"])
        ps = [h["price"] for h in hist]
        reg = regular_price(con, r["id"])
        best = money(sym, r["best_price"]) if r["best_price"] is not None else "-"
        hit = r["max_price"] is not None and r["best_price"] is not None and r["best_price"] <= r["max_price"]
        out.append("<tr><td>%s%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%d</td></tr>" % (
            _html.escape(r["keywords"]), f" <small>[{_html.escape(r['folder'])}]</small>" if r["folder"] else "",
            "g" if hit else "", best, _html.escape(r["best_store"] or "-"),
            money(sym, r["max_price"]) if r["max_price"] is not None else "-",
            money(sym, reg[0]) if reg else "-", money(sym, min(ps)) if ps else "-", len(ps)))
    out.append("</table>")
    return "".join(out)


UPDATE_FILES = ["DealScraper.pyw", "engine.py", "ui_kit.py", "README.md", "selftest.py"]
UPDATE_REQUIRED = ("DealScraper.pyw", "engine.py", "ui_kit.py")
UPDATE_FIXTURES = ["gift_card_badge.html", "jsonld_grid.html", "savings_noise.html", "was_price_cards.html", "jb_ticket.html"]
APP_DIR = Path(__file__).resolve().parent


def update_manifest(url: str) -> dict | None:
    """Read the update file. Line 1 = newest version, line 2 = download page, then optional 'note: ...' lines
    (what's new) and 'file: path' lines (extra files to download). None if it can't be read."""
    try:
        r = requests.get(url, timeout=(5, 8), headers={"User-Agent": "Deals-updater"})
        r.raise_for_status()
        lines = [ln.strip() for ln in r.text.strip().splitlines() if ln.strip()]
        m = {"version": int(lines[0]), "page": "", "notes": [], "files": [], "base": url.rsplit("/", 1)[0] + "/"}
        for ln in lines[1:]:
            low = ln.lower()
            if low.startswith("note:"):
                m["notes"].append(ln[5:].strip())
            elif low.startswith("file:"):
                m["files"].append(ln[5:].strip())
            elif low.startswith("http") and not m["page"]:
                m["page"] = ln
        return m
    except (requests.RequestException, ValueError, IndexError):
        return None


def release_manifest(repo: str | None = None) -> dict | None:
    """Newest GitHub release of the packaged app: {'version','page','notes','installer','sha_url'} or None."""
    repo = repo or GITHUB_REPO
    try:
        r = requests.get(f"{GITHUB_API}/repos/{repo}/releases/latest", timeout=(5, 10),
                         headers={"User-Agent": "Deals-updater", "Accept": "application/vnd.github+json"})
        r.raise_for_status()
        j = r.json()
        assets = {a["name"]: a["browser_download_url"] for a in j.get("assets", [])}
        notes = [re.sub(r"^(?:[-*]|note:)\s*", "", ln.strip(), flags=re.I) for ln in (j.get("body") or "").splitlines()
                 if re.match(r"\s*(?:[-*]\s+|note:)", ln, re.I)]
        return {"version": int(re.sub(r"\D", "", j["tag_name"])), "page": j.get("html_url", ""), "notes": notes,
                "installer": assets.get("Deals-Setup.exe"), "sha_url": assets.get("Deals-Setup.exe.sha256"), "files": [], "base": ""}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def fetch_update_manifest(settings: dict) -> dict | None:
    """The right update source: GitHub releases for the packaged .exe, the Version.txt file for the .pyw files."""
    return release_manifest() if FROZEN else update_manifest(settings.get("update_url", ""))


def download_installer(m: dict, progress=None) -> tuple[bool, str]:
    """Download Deals-Setup.exe for release `m`, check its SHA-256 against the published checksum, and return its path."""
    import hashlib
    if not m.get("installer"):
        return False, "this release has no installer attached yet"
    dest = Path(tempfile.mkdtemp(prefix="deals_update_")) / "Deals-Setup.exe"
    try:
        want = ""
        if m.get("sha_url"):
            want = requests.get(m["sha_url"], timeout=(6, 15), headers={"User-Agent": "Deals-updater"}).text.split()[0].lower()
        h, got = hashlib.sha256(), 0
        with requests.get(m["installer"], stream=True, timeout=(8, 30), headers={"User-Agent": "Deals-updater"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(got, total)
    except (requests.RequestException, OSError, IndexError) as e:
        return False, f"couldn't download the update ({type(e).__name__}) - check your internet connection and try again"
    if not want:
        return False, "the release has no checksum file, so it wasn't installed"
    if h.hexdigest().lower() != want:
        dest.unlink(missing_ok=True)
        return False, "the download didn't match its checksum (it may be corrupted), so it wasn't installed"
    with open(dest, "rb") as fh:
        if fh.read(2) != b"MZ" or got < 1_000_000:
            return False, "the downloaded file isn't a valid installer"
    return True, str(dest)


def clean_env() -> dict:
    """Environment for starting another copy of this program. A packaged app passes private variables to its children;
    if the new copy inherits them it tries to reuse the old copy's files (which are being replaced) and silently fails to open."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def prepare_for_installer() -> None:
    """Before the installer starts: close the hidden browser and stop every helper process that is running from Deals'
    own install folder (the browser driver, node.exe). Otherwise Setup lists them as 'in use' and cannot continue."""
    try:
        t = threading.Thread(target=BROWSER.reset, daemon=True)
        t.start()
        t.join(8)
    except Exception:  # noqa: BLE001
        pass
    if sys.platform != "win32" or not FROZEN:
        return
    try:
        here = str(Path(sys.executable).resolve().parent).replace("'", "''")
        me = os.getpid()
        ps = ("Get-Process | Where-Object { $_.Id -ne %d -and $_.Path -and $_.Path.StartsWith('%s\\') } | "
              "Stop-Process -Force -ErrorAction SilentlyContinue" % (me, here))
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
                       timeout=15, creationflags=0x08000000, env=clean_env(), capture_output=True)
    except Exception:  # noqa: BLE001
        pass


def run_installer(path: str) -> None:
    """Start the installer silently, detached from this process. The installer closes Deals if needed, installs over the
    old files (your data is kept in your user profile) and starts the new version."""
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0                  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/NORESTART"],
                     close_fds=True, creationflags=flags, env=clean_env())


def download_update(m: dict, app_dir=None, progress=None) -> tuple[bool, str]:
    """Download the new files, check them, back up the current ones, then swap them in. Nothing is touched unless every
    required file downloaded and compiles; if swapping fails part-way the old files are put back."""
    app_dir = Path(app_dir or APP_DIR)
    rels: list[str] = []
    for rel in UPDATE_FILES + ["Fixtures/" + f for f in UPDATE_FIXTURES] + list(m.get("files", [])):
        if rel not in rels:
            rels.append(rel)
    got: dict[str, bytes] = {}
    for i, rel in enumerate(rels):
        if progress:
            progress(i, len(rels))
        try:
            r = requests.get(m["base"] + quote(rel), timeout=(6, 30), headers={"User-Agent": "Deals-updater"})
        except requests.RequestException as e:
            return False, "couldn't reach the download address - check your internet connection and try again"
        if r.status_code == 404 and rel not in UPDATE_REQUIRED:
            continue
        if r.status_code != 200 or len(r.content) < 20:
            return False, f"couldn't download {rel} (error {r.status_code})"
        if rel.endswith((".py", ".pyw")):
            try:
                compile(r.content.decode("utf-8"), rel, "exec")
            except (SyntaxError, UnicodeDecodeError, ValueError):
                return False, f"{rel} arrived damaged, so nothing was changed"
        got[rel] = r.content
    if any(f not in got for f in UPDATE_REQUIRED):
        return False, "some required files were missing, so nothing was changed"
    if f"ENGINE_VERSION = {m['version']}".encode() not in got["engine.py"]:
        return False, "the new files don't match the announced version yet - try again in a few minutes"
    fix_dir = next((d for d in ("fixtures", "Fixtures") if (app_dir / d).is_dir()), "fixtures")
    dest = {rel: app_dir / (fix_dir + rel[len("Fixtures"):] if rel.startswith("Fixtures/") else rel) for rel in got}
    bdir = app_dir / "backup" / f"v{ENGINE_VERSION}_{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        for rel, path in dest.items():
            if path.exists():
                (bdir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, bdir / rel)
        for rel, path in dest.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".new")
            tmp.write_bytes(got[rel])
            os.replace(tmp, path)
    except OSError as e:
        for rel, path in dest.items():                 # put everything back
            if (bdir / rel).exists():
                try:
                    shutil.copy2(bdir / rel, path)
                except OSError:
                    pass
        return False, f"couldn't write the new files ({e}); your old files were restored"
    old = sorted((app_dir / "backup").glob("v*"))
    for d in old[:-3]:                                 # keep the three newest backups
        shutil.rmtree(d, ignore_errors=True)
    return True, f"Updated {len(got)} files. Your previous version is saved in the 'backup' folder."


def check_update(url: str) -> tuple[int | None, str]:
    """Reads a small text file at `url`: first line = newest engine version number, second line (optional) = download page."""
    try:
        lines = fetch(url, timeout=(5, 8)).strip().splitlines()
        return int(lines[0].strip()), (lines[1].strip() if len(lines) > 1 else "")
    except (FetchError, ValueError, IndexError):
        return None, ""


# --------------------------------------------------------------------------- #
# Daily summary + quiet hours
# --------------------------------------------------------------------------- #
def in_quiet(s: dict, now: float | None = None) -> bool:
    """True during the user's quiet hours (default 10pm-7am) when they have switched them on."""
    if str(s.get("quiet_on", "0")) != "1":
        return False
    try:
        a, b = int(float(s.get("quiet_start", 22))), int(float(s.get("quiet_end", 7)))
    except ValueError:
        return False
    h = time.localtime(now or time.time()).tm_hour
    return (a <= h < b) if a < b else (h >= a or h < b) if a != b else False


def hold_alerts(s: dict) -> bool:
    return s.get("alert_mode") == "summary" or in_quiet(s)


def send_pending(con, s: dict, log=print, now: float | None = None) -> int:
    """Send held alerts as ONE message: at the summary hour (summary mode) or once quiet hours end."""
    now = now or time.time()
    rows = con.execute("SELECT * FROM alerts WHERE notified=0 ORDER BY price DESC").fetchall()
    if not rows or in_quiet(s, now):
        return 0
    lt = time.localtime(now)
    if s.get("alert_mode") == "summary":
        try:
            hour = int(float(s.get("summary_hour", 8)))
        except ValueError:
            hour = 8
        today = time.strftime("%Y-%m-%d", lt)
        if lt.tm_hour < hour or s.get("summary_sent") == today:
            return 0
        set_setting(con, "summary_sent", today)
    sym = s.get("currency", "$")
    best: dict[str, sqlite3.Row] = {}
    for r in rows:                                   # one line per product (cheapest)
        k = r["keywords"]
        if k not in best or r["price"] < best[k]["price"]:
            best[k] = r
    lines = [f"- {r['title'][:70]}: {money(sym, r['price'])} at {r['store']}" + (f" ({r['reasons']})" if r["reasons"] else "")
             for r in list(best.values())[:12]]
    picks = []
    if s.get("alert_mode") == "summary":
        for r in con.execute("SELECT title,price,store,pct FROM picks WHERE kind='daily' ORDER BY found_at DESC, pct DESC LIMIT 3"):
            picks.append(f"* {r['title'][:60]}: {money(sym, r['price'])} at {r['store']} ({r['pct']:.0f}% off)")
    body = "\n".join(lines) + (("\n\nTop daily deals:\n" + "\n".join(picks)) if picks else "")
    n = len(best)
    notify(s, f"Deals summary: {n} item{'s' if n != 1 else ''} on sale", body, None, log)
    con.execute("UPDATE alerts SET notified=1 WHERE notified=0")
    con.commit()
    return len(rows)


# --------------------------------------------------------------------------- #
# Daily deals digest (opt in): fresh deals in the categories you picked, once a day
# --------------------------------------------------------------------------- #
DIGEST_MAX_CATS = 5


def digest_cats(s: dict) -> list[str]:
    try:
        v = json.loads(s.get("digest_cats") or "[]")
    except (ValueError, TypeError):
        v = []
    return [c for c in v if c in DAILY_CATS][:DIGEST_MAX_CATS]


def digest_due(s: dict, now: float | None = None) -> bool:
    """True once a day, after the chosen hour, when the digest is switched on and has categories."""
    if s.get("digest_on") != "1" or not digest_cats(s) or in_quiet(s, now):
        return False
    lt = time.localtime(now or time.time())
    try:
        hour = int(float(s.get("digest_hour", 8)))
    except ValueError:
        hour = 8
    return lt.tm_hour >= hour and s.get("digest_sent") != time.strftime("%Y-%m-%d", lt)


def run_digest(stores: list[dict], cfg: dict | None = None, log=print, cancel=None, force: bool = False,
               progress=None) -> dict | None:
    """Search ONLY the categories you chose, then send the best few in each as one message.
    Returns {'subject','body','url','n'} (also sent to your alert channels), or None when nothing was found."""
    con = db()
    s = get_settings(con)
    cats = digest_cats(s)
    if not cats or not stores:
        return None
    if not force:
        if not digest_due(s):
            return None
        set_setting(con, "digest_sent", time.strftime("%Y-%m-%d"))          # one attempt a day, whatever the outcome
    sym = s.get("currency", "$")
    t0, sections, first_url, total = time.time(), [], None, 0
    for i, cat in enumerate(cats):
        if cancel is not None and cancel.is_set():
            break
        if progress:
            progress(i, len(cats), cat)
        try:
            refresh_daily(stores, cfg, log=log, cancel=cancel, category=cat, sweep=8)
        except Exception as ex:  # noqa: BLE001
            log(f"digest: {cat} failed: {ex}")
            continue
        rows = [r for r in con.execute("SELECT title,price,store,pct,url,terms FROM picks WHERE kind='daily' AND found_at>=? "
                                       "ORDER BY pct DESC", (t0,)) if pick_category(r["terms"], r["title"]) == cat][:3]
        if rows:
            first_url = first_url or rows[0]["url"]
            total += len(rows)
            sections.append(cat + "\n" + "\n".join(
                f"- {r['title'][:70]}: {money(sym, r['price'])} at {r['store']} ({r['pct']:.0f}% off)\n  {r['url']}" for r in rows))
    if not sections:
        return None
    subject = f"Deals digest: {total} deal{'s' if total != 1 else ''} in " + ", ".join(c for c in cats if any(x.startswith(c + "\n") for x in sections))
    body = "\n\n".join(sections)
    notify(s, subject[:120], body, first_url, log)
    return {"subject": subject[:120], "body": body, "url": first_url, "n": total}


# --------------------------------------------------------------------------- #
# Deal score: one 0-100 number that says how good a listing really is
# --------------------------------------------------------------------------- #
def deal_score(o: Offer, prev: float | None = None, st: dict | None = None, info: dict | None = None,
               typical: float | None = None) -> tuple[int, str, list[str]]:
    """(score, label, reasons). Built from the real discount, how the price compares with its own history,
    reviews, the price against other shops, and OzBargain votes. Unverified 'was' prices score low."""
    pct, kind = deal_pct(o, prev)
    why: list[str] = []
    if not kind:
        return 0, "", []
    pts = 0.0
    if kind != "ozb":
        pts += min(45.0, (pct or 0) * 0.9)
        why.append(f"{pct:.0f}% off")
    verdict, _ = price_verdict(o, st)
    if verdict == "lowest":
        pts += 22
        why.append("lowest price we've seen")
    elif verdict == "inflated":
        pts = min(pts, 18) - 5
        why.append("was-price unverified")
    elif st and st.get("n", 0) >= 3 and st.get("median") and o.price <= st["median"] * 0.9:
        pts += 10
        why.append("below its usual price")
    if info:
        tone = review_verdict(info)[0]
        if tone == "good":
            pts += 15
            why.append("good reviews")
        elif tone == "ok":
            pts += 5
        elif tone == "poor":
            pts -= 20
            why.append("poor reviews")
    if typical and o.price < typical * 0.9 and not o.accessory:
        pts += 8
        why.append("cheaper than most shops")
    if o.source == "ozb":
        pts += 20 + min(15, max(0, o.votes) / 6)
        why.append(f"{o.votes:+d} votes")
    if o.accessory:
        pts -= 15
    sc = int(max(0, min(100, round(pts))))
    return sc, ("Great" if sc >= 75 else "Good" if sc >= 55 else "Fair" if sc >= 35 else "Weak"), why


# --------------------------------------------------------------------------- #
# Store health: do the parsers still find products on each store?
# --------------------------------------------------------------------------- #
SNAP_DIR = Path(DB_PATH).parent / "snapshots"


_SEARCH_PARAMS = ("q", "query", "search", "s", "keywords", "keyword", "term", "text", "k", "searchterm", "search_query",
                  "search_term", "searchtext", "kw", "search_text", "string")
_GENERIC_SEARCH = ["/search?q={query}", "/search/?q={query}", "/catalogsearch/result/?q={query}", "/search?query={query}",
                   "/search?type=product&q={query}", "/?s={query}&post_type=product", "/search?search={query}",
                   "/?rf=kw&kw={query}", "/search.php?search_query={query}", "/index.php?route=product/search&search={query}",
                   "/catalogsearch/result?q={query}", "/search?keywords={query}", "/search?term={query}", "/search?text={query}",
                   "/search?searchTerm={query}", "/search-results?q={query}", "/products?q={query}", "/shop/search?q={query}",
                   "/pages/search?q={query}", "/search/{query}"]
_PROBE = {"tech": "monitor", "gaming": "controller", "home": "pillow", "beauty": "moisturiser", "pets": "dog food",
          "toys": "lego", "sports": "shoes", "fashion": "shoes", "music": "guitar", "books": "cookbook", "baby": "pram",
          "all": "gift"}


def _home_candidates(base: str, cfg: dict) -> list[str]:
    """Search addresses the shop's own home page advertises: its search form, or its OpenSearch description."""
    try:
        page = fetch(base + "/", timeout=(5, 9))
    except FetchError as e:
        if e.kind not in ("blocked", "botcheck") or not browser_wanted(cfg):
            return []
        try:
            page = BROWSER.render(base + "/", 20)
        except FetchError:
            return []
    out: list[str] = []
    soup = make_soup(page)
    for f in soup.find_all("form"):
        if (f.get("method") or "get").lower() != "get":
            continue
        for inp in f.find_all("input"):
            name = (inp.get("name") or "").strip()
            if name.lower() in _SEARCH_PARAMS or (inp.get("type") or "").lower() == "search":
                if not name:
                    continue
                fixed = {i.get("name"): i.get("value") or "" for i in f.find_all("input", type="hidden") if i.get("name")}
                fixed[name] = "{query}"
                q = "&".join(f"{quote(k)}={v if v == '{query}' else quote(v)}" for k, v in fixed.items())
                out.append(urljoin(base + "/", f.get("action") or "/") .split("?")[0] + "?" + q)
                break
    for link in soup.find_all("link", rel=lambda r: r and "search" in r):
        href = link.get("href")
        if href and "opensearch" in (link.get("type") or ""):
            try:
                xml = fetch(urljoin(base + "/", href), timeout=(4, 7))
                for m in re.finditer(r'(?i)<Url[^>]+type="text/html"[^>]*template="([^"]+)"|<Url[^>]+template="([^"]+)"[^>]*type="text/html"', xml):
                    tpl = _html.unescape(m.group(1) or m.group(2)).replace("{searchTerms}", "{query}")
                    tpl = re.sub(r"\{[^}]*\?\}|&?[\w.-]+=\{(?!query)[^}]*\}", "", tpl)
                    out.append(tpl)
            except FetchError:
                pass
    return out


def discover_search_url(store: dict, cfg: dict | None = None, budget: float = 60.0) -> str | None:
    """Find a search address that works for `store` (home-page search form first, then common patterns).
    Returns a template containing {query}, or None."""
    cfg = cfg or {}
    pu = urlparse(str(store["search_url"]).replace("{query}", "x"))
    base = f"{pu.scheme}://{pu.netloc}"
    cats = (STORE_CATS.get(store["name"], "all") or "all").split()
    probe = _PROBE.get(cats[0], "gift")
    cands, t0 = [], time.time()
    for c in _home_candidates(base, cfg) + [base + g for g in _GENERIC_SEARCH]:
        if c not in cands and c != store["search_url"] and c != store.get("alt_url"):
            cands.append(c)
    for c in cands[:16]:
        if time.time() - t0 > budget:
            break
        trial = {"name": store["name"], "search_url": c, "alt_url": "", "item": None}
        try:
            offers = scrape_store(trial, probe, cfg, probe)
        except FetchError:
            continue
        except Exception:  # noqa: BLE001
            continue
        if len(offers) >= 2:
            return c
    return None


def repair_sources(con, cfg: dict | None = None, progress=None, only_names: list[str] | None = None) -> list[dict]:
    """Find working search addresses for sources that say 'Search URL not found' (switched on or off).
    Saves what it finds and switches the source back on. Returns [{name, ok, url}]."""
    cfg = cfg or {}
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM stores WHERE status LIKE 'Search URL%' OR status LIKE 'No products%' OR status LIKE 'Error%'")]
    rows = [r for r in rows if not str(r["search_url"]).startswith("ozb:") and "staticice." not in r["search_url"]]
    if only_names:
        rows = [r for r in rows if r["name"] in only_names]
    out: list[dict] = []
    if not rows:
        return out
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(discover_search_url, r, cfg): r for r in rows}
        for i, (fut, r) in enumerate(futs.items(), 1):
            try:
                url = fut.result()
            except Exception:  # noqa: BLE001
                url = None
            if url:
                con.execute("UPDATE stores SET alt_url=?, enabled=1, status='Not tested', fail_streak=0, skip_until=0 WHERE id=?",
                            (url, r["id"]))
            out.append({"name": r["name"], "ok": bool(url), "url": url or ""})
            if progress:
                progress(i, len(rows))
    con.commit()
    return out


def health_check(stores: list[dict], cfg: dict | None = None, progress=None, query: str = "tv") -> list[dict]:
    """Search every store for a common product. Returns [{name, status, count, ms}]; a store that returns a page
    but no products has its page saved to snapshots/ so a changed layout can be looked at."""
    cfg = cfg or {}
    out: list[dict] = []

    def one(st):
        t0 = time.time()
        try:
            offs = scrape_store(st, query, cfg)
            bad = [o for o in offs if not o.price or o.price <= 0]
            status = "ok" if len(offs) >= 3 and not bad else "few" if offs else "none"
            return {"name": st["name"], "status": status, "count": len(offs), "ms": int((time.time() - t0) * 1000), "err": ""}
        except FetchError as e:
            return {"name": st["name"], "status": e.kind, "count": 0, "ms": int((time.time() - t0) * 1000), "err": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"name": st["name"], "status": "error", "count": 0, "ms": 0, "err": str(e)}

    with ThreadPoolExecutor(max_workers=POOL_WORKERS) as ex:
        futs = [ex.submit(one, st) for st in stores]
        for i, f in enumerate(futs, 1):
            out.append(f.result())
            if progress:
                progress(i, len(futs))
    for r, st in zip(out, stores):
        if r["status"] == "none" and not str(st["search_url"]).startswith(("ozb:",)) and "staticice." not in st["search_url"]:
            try:
                SNAP_DIR.mkdir(exist_ok=True)
                page = fetch(st["search_url"].replace("{query}", quote_plus(query)), timeout=(6, 10))
                (SNAP_DIR / (re.sub(r"\W+", "_", st["name"]) + ".html")).write_text(page[:300000], encoding="utf-8")
                r["snap"] = True
            except Exception:  # noqa: BLE001
                pass
    return out


# --------------------------------------------------------------------------- #
# Daily deals + "For you" discovery
# --------------------------------------------------------------------------- #
DAILY_MIN_PRICE = 150.0     # "expensive" = at least this much
DAILY_MIN_PCT = 25.0        # "great discount" = at least this much off
FORYOU_MIN_PCT = 8.0
DAILY_QUERIES = ["tv", "laptop", "monitor", "headphones", "soundbar", "fridge", "washing machine", "dishwasher",
                 "robot vacuum", "coffee machine", "mattress", "power tool", "e-bike", "iphone", "camera",
                 "air fryer", "treadmill", "lawn mower", "smartwatch", "gaming console", "tablet", "dryer",
                 "air conditioner", "vacuum cleaner", "drill", "bbq", "sofa", "bike", "speaker", "printer",
                 "gaming laptop", "graphics card", "ssd", "wireless earbuds", "projector", "dyson", "pressure washer",
                 "tool kit", "golf", "camping tent", "pram", "perfume", "sneakers", "backpack", "microwave", "oven"]
DAILY_CATS = {
    "Tech": ["tv", "laptop", "monitor", "headphones", "soundbar", "tablet", "wireless earbuds", "projector", "ssd", "router",
             "keyboard", "iphone", "samsung phone", "smartwatch", "printer", "nas", "power bank", "wifi mesh"],
    "Gaming": ["gaming console", "gaming laptop", "gaming monitor", "gaming headset", "gaming chair", "nintendo switch",
               "ps5", "xbox", "steam deck", "graphics card", "gaming mouse", "gaming keyboard"],
    "Home & kitchen": ["fridge", "washing machine", "dishwasher", "dryer", "coffee machine", "air fryer", "robot vacuum",
                       "vacuum cleaner", "microwave", "oven", "dyson", "mattress", "sofa", "air conditioner", "heater",
                       "thermomix", "blender", "dehumidifier"],
    "Tools & DIY": ["drill", "power tool", "tool kit", "impact driver", "angle grinder", "circular saw", "pressure washer",
                    "tool box", "welder", "air compressor", "laser level", "ladder"],
    "Garden & BBQ": ["lawn mower", "bbq", "whipper snipper", "chainsaw", "hedge trimmer", "leaf blower", "outdoor furniture",
                     "pizza oven", "fire pit", "garden hose", "ride on mower"],
    "Fitness": ["treadmill", "exercise bike", "dumbbells", "weight bench", "rowing machine", "yoga mat", "fitness tracker",
                "running shoes", "gps watch", "home gym", "massage gun"],
    "Cycling": ["bike", "e-bike", "mountain bike", "road bike", "bike helmet", "bike trainer", "cycling computer",
                "electric scooter", "kids bike"],
    "Golf": ["golf clubs", "golf driver", "golf irons", "golf bag", "golf shoes", "golf rangefinder", "golf buggy",
             "golf putter", "golf simulator"],
    "Outdoor & camping": ["camping tent", "sleeping bag", "esky", "camping stove", "swag", "hiking boots", "kayak",
                          "paddle board", "fishing rod", "fishing reel", "4wd", "camp chair", "portable fridge"],
    "Fashion": ["sneakers", "jacket", "jeans", "backpack", "sunglasses", "boots", "hoodie", "handbag", "watch", "wallet"],
    "Luxury": ["gucci bag", "louis vuitton", "chanel", "prada", "cartier", "rolex", "omega watch", "tag heuer", "pandora",
               "swarovski", "designer handbag", "designer sunglasses", "michael kors", "coach bag"],
    "Fragrance": ["dior sauvage", "chanel perfume", "ysl perfume", "versace perfume", "creed aventus", "tom ford perfume",
                  "paco rabanne", "jean paul gaultier", "hugo boss fragrance", "calvin klein fragrance", "womens perfume",
                  "mens cologne", "perfume gift set"],
    "Beauty & health": ["perfume", "hair dryer", "hair straightener", "electric toothbrush", "skincare", "electric shaver",
                        "vitamins", "protein powder"],
    "Baby & kids": ["pram", "car seat", "cot", "high chair", "baby monitor", "trampoline", "kids bike", "bassinet"],
    "Toys & hobbies": ["lego", "board game", "rc car", "model kit", "puzzle", "telescope", "3d printer", "sewing machine",
                       "drone", "train set", "craft"],
    "Pets": ["dog bed", "cat tree", "dog food", "aquarium", "pet fountain", "dog crate", "robot litter box"],
    "Car & auto": ["dash cam", "tyres", "car battery", "jump starter", "roof rack", "car vacuum", "car stereo", "tow bar"],
    "Music": ["guitar", "electric guitar", "digital piano", "drum kit", "guitar amp", "dj controller", "ukulele",
              "microphone", "synthesizer"],
    "Photography": ["camera", "mirrorless camera", "camera lens", "gopro", "tripod", "action camera", "drone", "gimbal"],
}
DAILY_CAT_NAMES = ["All"] + list(DAILY_CATS)
QUERY_CAT: dict[str, str] = {}
for _c, _qs in DAILY_CATS.items():
    for _q in _qs:
        QUERY_CAT.setdefault(_q, _c)
for _q in ["tv", "laptop", "monitor", "headphones", "soundbar", "tablet"]:
    QUERY_CAT[_q] = "Tech"


def pick_category(terms: str, title: str) -> str:
    """Which Daily deals category a saved pick belongs to (by the search that found it, else by words in its title)."""
    if terms and terms in QUERY_CAT:
        return QUERY_CAT[terms]
    t = (title or "").lower()
    best, hit = "Other", 0
    for c, qs in DAILY_CATS.items():
        for q in qs:
            if len(q) >= 4 and q in t and len(q) > hit:
                best, hit = c, len(q)
    return best


DAILY_SWEEP = 22            # categories checked per refresh, picked at random so each refresh shows different things
DAILY_KEEP = 150
SIBLINGS = {"headphones": ["earbuds", "speaker", "soundbar"], "earbuds": ["headphones"], "tv": ["soundbar", "monitor", "projector"],
            "laptop": ["tablet", "monitor"], "monitor": ["laptop", "tv"], "phone": ["earbuds", "smartwatch"],
            "iphone": ["airpods", "smartwatch"], "drill": ["impact driver", "saw", "grinder"], "vacuum": ["robot vacuum", "air purifier"],
            "fridge": ["freezer", "dishwasher"], "camera": ["lens", "drone"], "console": ["controller", "headset"],
            "playstation": ["controller", "headset"], "watch": ["smartwatch"], "smartwatch": ["watch"], "bike": ["helmet", "e-bike"],
            "coffee": ["espresso machine"], "mattress": ["pillow", "quilt"], "speaker": ["soundbar", "headphones"],
            "shoes": ["sneakers", "boots"], "sneakers": ["shoes"], "mower": ["whipper snipper", "blower"],
            "keyboard": ["mouse"], "mouse": ["keyboard"]}
DAILY_EVERY = 20 * 3600     # refreshed at most about once a day
FORYOU_ADD = 24             # new suggestions per refresh: it fills up slowly, on purpose


def _saving(o: Offer) -> float:
    base = o.was_price or o.ref_price or 0
    return max(0.0, base - o.price)


def _great(o: Offer, min_price: float, min_pct: float, prev: dict | None = None, allow_ozb: bool = False) -> float | None:
    """Percent off when `o` is a real, strong discount worth showing; else None."""
    if o.accessory or o.used or o.oos or o.price < min_price:
        return None
    pct, kind = deal_pct(o, (prev or {}).get(o.url))
    if kind == "ozb" and allow_ozb:
        return 10.0                                    # a vetted community deal with nothing to compare against
    if kind in (None, "ozb") or pct is None or pct < min_pct or pct > 90:
        return None
    return pct


def _store_pick(con, kind: str, o: Offer, pct: float, terms: str = ""):
    base = o.was_price or o.ref_price
    con.execute("INSERT OR REPLACE INTO picks(kind,url,store,title,price,was,pct,image,source,expires,votes,terms,found_at,basis)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (kind, o.url, o.store, o.title, o.price, base, pct, o.image, o.source, o.expires, o.votes,
                 terms, time.time(), "was" if o.was_price else "ref"))


def pick_offers(con, kind: str, limit: int = 200, category: str = "All") -> list[Offer]:
    """Saved picks as Offers (a 'was' price is stored so the normal card shows the saving)."""
    # "Not interested" hides a pick everywhere; on For you, "Interested" also takes it off the page (it is remembered for taste)
    fb = {r["url"] for r in con.execute("SELECT url FROM feedback" + ("" if kind == "foryou" else " WHERE verdict='no'"))}
    rows = con.execute("SELECT * FROM picks WHERE kind=? ORDER BY found_at DESC, pct DESC LIMIT ?", (kind, limit * 3 if category != "All" else limit)).fetchall()
    out = []
    for r in rows:
        if r["url"] in fb:
            continue
        if r["expires"] and r["expires"] < time.time():
            continue
        if kind == "daily" and category != "All" and pick_category(r["terms"], r["title"]) != category:
            continue
        ref = r["basis"] == "ref"
        out.append(Offer(r["store"], r["title"], r["price"], r["url"], None if ref else r["was"], r["image"],
                         expires=r["expires"], votes=r["votes"] or 0, source=r["source"] or "store",
                         ref_price=r["was"] if ref else None))
    if kind == "daily":
        out.sort(key=_saving, reverse=True)
    return out


def picks_age(con, kind: str) -> float | None:
    r = con.execute("SELECT MAX(found_at) m FROM picks WHERE kind=?", (kind,)).fetchone()
    return (time.time() - r["m"]) if r and r["m"] else None


def refresh_daily(stores: list[dict], cfg: dict | None = None, progress=None, log=print, cancel=None, category: str = "All",
                  sweep: int | None = None) -> int:
    """Big-ticket items that are a long way below their normal price today. Returns how many were found."""
    con = db()
    cfg = dict(cfg or {}, _cancel=cancel)
    cat = category if category in DAILY_CATS else "All"
    pool = DAILY_CATS[cat] if cat != "All" else DAILY_QUERIES
    min_price = DAILY_MIN_PRICE if cat == "All" else min(DAILY_MIN_PRICE, 60.0)    # hobby gear is often cheaper
    queries = [(q, q) for q in random.sample(pool, min(sweep or DAILY_SWEEP, len(pool)))]
    res = find_offers_many(queries, stores, cfg, progress=progress, deadline=150.0)
    if _cancelled(cfg):
        return 0
    found: dict[str, tuple[Offer, float]] = {}
    via: dict[str, str] = {}
    for q, (ranked, _rep) in res.items():
        prev = last_prices(con, [o.url for o in ranked])
        for o in ranked:
            if o.score < ALERT_MIN_SCORE:
                continue
            pct = _great(o, min_price, DAILY_MIN_PCT, prev)
            if pct is not None and (o.url not in found or _saving(o) > _saving(found[o.url][0])):
                found[o.url] = (o, pct)
                via[o.url] = q
    # OzBargain front page: only posts that state both a deal price and a normal price
    try:
        for o in parse_ozb_feed(fetch_cached(f"{OZB_BASE}/deals/feed", ttl=600,
                                             accept="application/rss+xml,application/xml,text/xml,*/*", ua=OZB_UA)):
            if o.was_price and o.price >= min_price and (cat == "All" or pick_category("", o.title) == cat):
                pct = 100 * (o.was_price - o.price) / o.was_price
                if DAILY_MIN_PCT <= pct <= 90 and o.url not in found:
                    found[o.url] = (o, pct)
    except FetchError as e:
        log(f"OzBargain front page: {e}")
    fb = {r["url"] for r in con.execute("SELECT url FROM feedback WHERE verdict='no'")}
    best = sorted((v for u, v in found.items() if u not in fb), key=lambda v: _saving(v[0]), reverse=True)[:DAILY_KEEP]
    if cat == "All":
        con.execute("DELETE FROM picks WHERE kind='daily'")
    else:                                              # a category search only replaces that category's picks
        for r in con.execute("SELECT url, terms, title FROM picks WHERE kind='daily'").fetchall():
            if pick_category(r["terms"], r["title"]) == cat:
                con.execute("DELETE FROM picks WHERE kind='daily' AND url=?", (r["url"],))
    for o, pct in best:
        _store_pick(con, "daily", o, pct, via.get(o.url, ""))
    con.commit()
    return len(best)


# ---- interests: learned from the watchlist and from Interested / Not interested clicks ----
def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower()) if t not in STOP]


def _is_brand(t: str) -> bool:
    n = norm(t)
    return n in BRANDS or n in BRAND_ALIASES


def _type_words(text: str) -> list[str]:
    """Product-type words in some text ('headphones', 'drill'), in order, without brands or model numbers."""
    out = []
    for t in _tokens(text):
        base = t if t in WORD_CATS else t.rstrip("s")
        if base in WORD_CATS and not _is_brand(t) and not any(c.isdigit() for c in t) and base not in out:
            out.append(base)
    return out


def _brand_words(text: str) -> list[str]:
    return [norm(t) for t in _tokens(text) if _is_brand(t)]


def kind_key(title: str) -> tuple[str, str]:
    """(brand, product type) of a title, e.g. ('sony', 'headphones'). Either may be ''."""
    return ((_brand_words(title) or [""])[0], (_type_words(title) or [""])[0])


def set_feedback(con, o_url: str, verdict: str, title: str) -> list[str]:
    """verdict: 'yes' (interested) or 'no' (not interested). 'No' also clears the suggestions that are the same kind of
    thing (same brand and type); returns the addresses removed from the page."""
    terms = " ".join(_type_words(title)[:2] + _brand_words(title)[:1])
    con.execute("INSERT OR REPLACE INTO feedback(url,verdict,terms,title,at) VALUES(?,?,?,?,?)",
                (o_url, verdict, terms, title, time.time()))
    removed: list[str] = []
    if verdict == "no":
        key = kind_key(title)
        for r in con.execute("SELECT url, title FROM picks WHERE kind='foryou'").fetchall():
            if r["url"] == o_url or (key[0] and key[1] and kind_key(r["title"]) == key):
                removed.append(r["url"])
        for u in removed:
            con.execute("DELETE FROM picks WHERE kind='foryou' AND url=?", (u,))
    con.commit()
    return removed


def feedback_note(title: str, verdict: str) -> str:
    """What the app took from a click, in words ('Noted - looking for more Sony headphones')."""
    b, t = kind_key(title)
    what = " ".join(x for x in (b.title(), t) if x) or "things like that"
    return f"Noted - looking for more {what}" if verdict == "yes" else f"Got it - fewer {t or what} like that"


def liked_queries(con, limit: int = 8) -> list[str]:
    """Searches built from what you pressed Interested on (newest first): brand + type, then the type alone."""
    out: list[str] = []
    for r in con.execute("SELECT title FROM feedback WHERE verdict='yes' ORDER BY at DESC LIMIT 30"):
        b, t = kind_key(r["title"] or "")
        for q in ([f"{b} {t}"] if b and t else []) + ([t] if t else []):
            if q and q not in out:
                out.append(q)
        if len(out) >= limit:
            break
    return out[:limit]


def _taste(con) -> dict:
    """Counts of liked / disliked product types and brands."""
    t = {"like_types": {}, "no_types": {}, "like_brands": {}, "no_brands": {}}
    for r in con.execute("SELECT verdict, title FROM feedback"):
        yes = r["verdict"] == "yes"
        for w in _type_words(r["title"] or "")[:2]:
            d = t["like_types" if yes else "no_types"]
            d[w] = d.get(w, 0) + 1
        for b in _brand_words(r["title"] or "")[:1]:
            d = t["like_brands" if yes else "no_brands"]
            d[b] = d.get(b, 0) + 1
    return t


RANDOM_TOPICS = ["headphones", "air fryer", "monitor", "robot vacuum", "smartwatch", "laptop", "coffee machine", "tv",
                 "soundbar", "router", "keyboard", "mouse", "office chair", "standing desk", "power tools", "drill",
                 "camera", "drone", "tablet", "phone", "speaker", "gaming console", "ssd", "backpack", "sneakers",
                 "kettle", "blender", "dyson", "fridge", "washing machine", "mattress", "lego", "fitness tracker",
                 "e-bike", "bbq", "projector", "printer", "graphics card", "microwave", "electric toothbrush",
                 "vacuum cleaner", "tent", "board game", "toaster", "heater", "fan", "pressure cooker", "webcam"]


def reset_foryou(con):
    """Forget everything For you has learned (likes, dislikes, suggestions). Until you press Interested on something or add a
    new watchlist item, it suggests random popular things."""
    con.execute("DELETE FROM feedback")
    con.execute("DELETE FROM foryou_seen")
    con.execute("DELETE FROM picks WHERE kind='foryou'")
    wid = con.execute("SELECT COALESCE(MAX(id),0) FROM watchlist").fetchone()[0]
    set_setting(con, "foryou_rot", "0")
    set_setting(con, "foryou_reset_wid", str(wid))
    set_setting(con, "foryou_reset_at", str(time.time()))
    con.commit()


def foryou_random(con) -> bool:
    """True after a reset, until you mark something Interested or add a new item to the watchlist."""
    st = get_settings(con)
    at = float(st.get("foryou_reset_at") or 0)
    if not at:
        return False
    if con.execute("SELECT 1 FROM feedback WHERE verdict='yes' AND at >= ? LIMIT 1", (at,)).fetchone():
        return False
    wid = int(float(st.get("foryou_reset_wid") or 0))
    return not con.execute("SELECT 1 FROM watchlist WHERE id > ? LIMIT 1", (wid,)).fetchone()


def interest_queries(con) -> list[str]:
    """Searches that look for things like what you've saved or liked (not the exact items, to find new ones)."""
    if foryou_random(con):
        import random
        return random.sample(RANDOM_TOPICS, 8)
    taste = _taste(con)
    qs: list[str] = []
    for r in con.execute("SELECT keywords FROM watchlist ORDER BY id"):
        types = _type_words(r["keywords"])
        if types:
            q = " ".join(types[:2])
        else:
            q = " ".join(t for t in _tokens(r["keywords"]) if not _is_brand(t) and not any(c.isdigit() for c in t))
        if q:
            qs.append(q)
    for w, n in sorted(taste["like_types"].items(), key=lambda kv: -kv[1]):
        qs.append(w)
    for q in list(qs):                                 # neighbouring kinds of product widen what it can suggest
        for w in q.split():
            qs.extend(SIBLINGS.get(w, [])[:2])
    out = []
    for q in qs:
        words = q.split()
        if any(taste["no_types"].get(w, 0) >= 2 and not taste["like_types"].get(w) for w in words):
            continue                                   # you keep saying no to this kind of thing
        if q not in out:
            out.append(q)
    return out


FORYOU_IDLE_SHIFT = 5      # "Find more" this many times with no reaction -> move on to other categories


def _explore_topics(con, qs: list[str], n: int) -> list[str]:
    """Kinds of product you haven't been shown: neighbours of what you like first, then anything popular."""
    import random
    taste = _taste(con)
    seen = {w for q in qs for w in q.split()}
    bad = {w for w, c in taste["no_types"].items() if c >= 2 and not taste["like_types"].get(w)}
    near = [x for q in qs[:8] for w in q.split() for x in SIBLINGS.get(w, [])]
    pool = list(RANDOM_TOPICS)
    random.shuffle(pool)
    out: list[str] = []
    for t in near + pool:
        words = set(t.split())
        if t in qs or t in out or words & bad or (t in pool and words & seen and t not in near):
            continue
        out.append(t)
        if len(out) >= n:
            break
    return out


def _foryou_take(con, qs: list[str], off: int, st: dict) -> list[str]:
    """Which searches this 'Find more' runs: mostly your taste, plus a couple of outliers; after several presses with no
    Interested / Not interested (and nothing new on the watchlist) it swaps to other categories altogether."""
    if foryou_random(con):
        return [qs[(off + i) % len(qs)] for i in range(min(6, len(qs)))]
    sig = "%s:%s:%s" % (con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
                        con.execute("SELECT COALESCE(MAX(id),0) FROM watchlist").fetchone()[0],
                        con.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0])
    idle = int(st.get("foryou_idle") or 0) + 1 if st.get("foryou_sig") == sig else 0
    set_setting(con, "foryou_sig", sig)
    if idle >= FORYOU_IDLE_SHIFT:
        set_setting(con, "foryou_idle", "0")
        fresh = _explore_topics(con, qs, 6)
        if fresh:
            return fresh
    else:
        set_setting(con, "foryou_idle", str(idle))
    n_out = 2 if len(qs) >= 4 else 1
    liked = liked_queries(con)
    liked_sel = [liked[(off + i) % len(liked)] for i in range(min(3, len(liked)))]      # what you said yes to gets half the slots
    base = [q for q in qs if q not in liked_sel]
    main = [base[(off + i) % len(base)] for i in range(min(6 - n_out - len(liked_sel), len(base)))] if base else []
    return liked_sel + main + _explore_topics(con, qs + liked_sel + main, n_out)


def refresh_foryou(stores: list[dict], cfg: dict | None = None, progress=None, log=print, cancel=None) -> tuple[int, str]:
    """Look for deals similar to what you follow and like. Each press replaces the page with a fresh set."""
    con = db()
    cfg = dict(cfg or {})
    qs = interest_queries(con)
    if not qs:
        return 0, "Add something to your Watchlist (or mark a few Daily deals as Interested) and I'll start suggesting things."
    st = get_settings(con)
    off = int(st.get("foryou_rot") or 0)
    take = _foryou_take(con, qs, off, st)
    set_setting(con, "foryou_rot", str(off + len(take)))
    cfg = dict(cfg or {}, _cancel=cancel)
    res = find_offers_many([(q, q) for q in take], stores, cfg, progress=progress, deadline=90.0)
    if _cancelled(cfg):
        return 0, ""
    cands = _foryou_candidates(con, res, set(liked_queries(con)))
    added, per_q, chosen = 0, {}, []
    for _, o, pct, q in cands:
        if per_q.get(q, 0) >= max(4, FORYOU_ADD // max(1, len(take)) + 2):
            continue
        per_q[q] = per_q.get(q, 0) + 1
        chosen.append((o, pct, q))
        if len(chosen) >= FORYOU_ADD:
            break
    if chosen:                                              # a fresh page: what was on it before has had its chance
        now = time.time()
        for r in con.execute("SELECT url FROM picks WHERE kind='foryou'").fetchall():
            con.execute("INSERT OR REPLACE INTO foryou_seen(url, at) VALUES(?,?)", (r["url"], now))
        con.execute("DELETE FROM picks WHERE kind='foryou'")
        for o, pct, q in chosen:
            _store_pick(con, "foryou", o, pct, q)
        added = len(chosen)
    con.execute("DELETE FROM foryou_seen WHERE at < ?", (time.time() - 45 * 86400,))
    con.commit()
    return added, ("" if added else "Nothing new and well-discounted today. Check back tomorrow.")


def _foryou_candidates(con, res: dict, liked_qs: set) -> list:
    """Scored suggestions from search results: well discounted, not seen before, matching what you like and
    leaving out the kinds of thing you said no to."""
    taste = _taste(con)
    seen_fb = {r["url"] for r in con.execute("SELECT url FROM feedback")}
    seen_fb |= {r["url"] for r in con.execute("SELECT url FROM foryou_seen")}
    have = {r["url"] for r in con.execute("SELECT url FROM picks WHERE kind='foryou'")}
    no_keys = {kind_key(r["title"] or "") for r in con.execute("SELECT title FROM feedback WHERE verdict='no'")}
    bad_types = {w for w, c in taste["no_types"].items() if c >= 2 and not taste["like_types"].get(w)}
    watch_models = [[norm(t) for t in _tokens(r["keywords"]) if any(c.isdigit() for c in t)]
                    for r in con.execute("SELECT keywords FROM watchlist")]
    cands: list = []
    med: dict[str, float] = {}
    for q, (ranked, _rep) in res.items():
        prev = last_prices(con, [o.url for o in ranked])
        pool = sorted(o.price for o in ranked if o.score >= ALERT_MIN_SCORE and not o.accessory and o.source != "ozb")
        if len(pool) >= 4:
            med[q] = pool[len(pool) // 2]
        for o in ranked:
            if o.score < ALERT_MIN_SCORE or o.url in seen_fb or o.url in have:
                continue
            pct = _great(o, 20.0, FORYOU_MIN_PCT, prev, allow_ozb=True)
            if pct is None and med.get(q) and o.price >= 20 and o.price <= 0.93 * med[q]:
                pct = 100 * (1 - o.price / med[q])     # cheaper than most shops, even without a "was" price
                o.ref_price = med[q]
            if pct is None:
                continue
            nt = norm(o.title)
            if any(m and all(x in nt for x in m) for m in watch_models):
                continue                               # that's one you're already watching
            br, ty = kind_key(o.title)
            if (br, ty) in no_keys and br and ty:
                continue                               # you said no to this brand's version of this thing
            if set(_type_words(o.title)[:2]) & bad_types:
                continue
            if taste["no_brands"].get(br, 0) >= 2 and not taste["like_brands"].get(br):
                continue
            liked_type = any(w in taste["like_types"] for w in _type_words(o.title)[:2])
            bonus = (10 * min(2, taste["like_brands"].get(br, 0)) + (8 if liked_type else 0)
                     + (6 if q in liked_qs else 0) + (4 if o.source == "ozb" else 0))
            cands.append((pct + bonus, o, pct, q))
    cands.sort(key=lambda c: c[0], reverse=True)
    return cands


def more_like(title: str, stores: list[dict], cfg: dict | None = None, cancel=None, add: int = 3) -> int:
    """Right after you press Interested: look straight away for similar discounted things and put them on the page."""
    con = db()
    b, t = kind_key(title)
    q = " ".join(x for x in (b, t) if x) or " ".join(_tokens(title)[:3])
    if not q:
        return 0
    cfg = dict(cfg or {}, _cancel=cancel)
    res = find_offers_many([(q, q)], stores, cfg, deadline=30.0)
    if _cancelled(cfg):
        return 0
    cands = _foryou_candidates(con, res, {q})
    n = 0
    for _, o, pct, qq in cands[:add]:
        _store_pick(con, "foryou", o, pct, qq)
        n += 1
    con.commit()
    return n


def keywords_from_title(title: str) -> str:
    """Turn a product title into watchlist keywords: brand + model words, without marketing fluff."""
    t = re.sub(r"(?i)\b(?:bonus|free)\b.*?(?:gift\s*cards?|vouchers?)", " ", title)
    t = re.sub(r"[\[\(].*?[\]\)]", " ", t)
    t = re.sub(r"(?i)@.*$|\$\s?\d[\d,.]*|\b(?:save|was|rrp|now|only|sale|deal|ozbargain)\b", " ", t)
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\.\"']*", t) if w.lower() not in STOP]
    return " ".join(words[:6]).strip()


def add_to_watchlist(con, title: str) -> tuple[bool, str]:
    """Add a product to the watchlist from its title. Returns (added, keywords)."""
    kw = keywords_from_title(title)
    if not kw:
        return False, ""
    have = {norm(r["keywords"]) for r in con.execute("SELECT keywords FROM watchlist")}
    if norm(kw) in have:
        return False, kw
    con.execute("INSERT INTO watchlist(keywords) VALUES(?)", (kw,))
    con.commit()
    return True, kw


# --------------------------------------------------------------------------- #
# Reviews: product-page star ratings + what people say on Reddit
# --------------------------------------------------------------------------- #
REVIEW_MODES = ["Off", "Show ratings", "Hide poor reviews", "Only 4 stars and up"]
REVIEW_TTL = 7 * 86400
_RATING_TXT = re.compile(r"(?i)(\d(?:\.\d)?)\s*(?:out of|/)\s*5\b")
_COUNT_TXT = re.compile(r"(?i)\(?(\d[\d,]*)\)?\s*(?:customer\s+)?(?:reviews?|ratings?)\b")


def _agg(d):
    """Find an aggregateRating in schema.org data. Returns (rating out of 5, review count) or None."""
    if isinstance(d, list):
        for x in d:
            r = _agg(x)
            if r:
                return r
    elif isinstance(d, dict):
        a = d.get("aggregateRating")
        if isinstance(a, dict):
            try:
                val = float(str(a.get("ratingValue")).replace(",", "."))
                best = float(a.get("bestRating") or 5)
                cnt = int(float(str(a.get("reviewCount") or a.get("ratingCount") or 0).replace(",", "")))
                if best > 0 and val > 0:
                    return round(5 * val / best, 2), cnt
            except (TypeError, ValueError):
                pass
        for v in d.values():
            if isinstance(v, (dict, list)):
                r = _agg(v)
                if r:
                    return r
    return None


def parse_rating(page: str) -> tuple[float, int] | None:
    """Star rating (out of 5) and number of reviews from a product page, or None if it shows none."""
    page = page[:1_500_000]
    for m in re.finditer(r'(?is)<script[^>]+ld\+json[^>]*>(.*?)</script>', page):
        try:
            r = _agg(json.loads(m.group(1)))
        except (json.JSONDecodeError, ValueError):
            continue
        if r:
            return r
    m = re.search(r'(?i)itemprop=["\']ratingValue["\'][^>]*?content=["\']([\d.,]+)', page) or \
        re.search(r'(?i)content=["\']([\d.,]+)["\'][^>]*?itemprop=["\']ratingValue', page)
    if m:
        try:
            c = re.search(r'(?i)itemprop=["\'](?:reviewCount|ratingCount)["\'][^>]*?content=["\'](\d+)', page)
            return float(m.group(1).replace(",", ".")), int(c.group(1)) if c else 0
        except ValueError:
            pass
    m = _RATING_TXT.search(page)
    if m:
        c = _COUNT_TXT.search(page)
        try:
            return float(m.group(1)), int(c.group(1).replace(",", "")) if c else 0
        except ValueError:
            return None
    return None


_POS = ("recommend", "great", "solid", "love", "happy with", "reliable", "worth it", "worth the", "excellent", "best ",
        "fantastic", "no issues", "no problems", "works well", "good value", "impressed", "rock solid", "highly rated",
        "can't fault", "cant fault", "bang for")
_NEG = ("avoid", "returned", "return it", "garbage", "terrible", "broke", "broken", "died", "dies", "unreliable",
        "overpriced", "drop out", "dropouts", "dropping out", "waste of", "regret", "disappoint", "faulty", "crap",
        "junk", "cheap plastic", "not worth", "stay away", "buggy", "constantly", "rubbish", "dead after", "lemon")
_REDDIT = {"until": 0.0}
_REDDIT_LOCK = threading.Lock()


def reddit_sentiment(query: str) -> tuple[str, int] | None:
    """What Reddit posts about this product say: ('positive' | 'mixed' | 'negative', posts used), else None.
    Reddit often refuses automated requests; when it does we stop asking for a while and carry on without it."""
    if time.time() < _REDDIT["until"]:
        return None
    toks = [norm(t) for t in query.split()[:4] if norm(t)]
    if not toks:
        return None
    url = "https://www.reddit.com/search.json?" + urlencode({"q": f"{query} review", "limit": 25, "sort": "relevance", "t": "all"})
    with _REDDIT_LOCK:                                  # one at a time, politely spaced
        if time.time() < _REDDIT["until"]:
            return None
        try:
            r = _SESSION.get(url, headers={"User-Agent": OZB_UA, "Accept": "application/json"}, timeout=(5, 8))
            time.sleep(0.7)
        except requests.RequestException:
            _REDDIT["until"] = time.time() + 600
            return None
        if r.status_code in (401, 403, 429):
            _REDDIT["until"] = time.time() + 1800
            return None
        if r.status_code != 200:
            return None
        try:
            posts = [c["data"] for c in r.json()["data"]["children"]]
        except (ValueError, KeyError, TypeError):
            return None
    pos = neg = 0.0
    used = 0
    need = max(1, int(len(toks) * 0.6 + 0.99))
    for p in posts:
        text = f"{p.get('title', '')} {(p.get('selftext') or '')[:700]}"
        nt = norm(text)
        if sum(1 for t in toks if t in nt) < need:
            continue
        low = text.lower()
        w = 1 + math.log1p(max(0, int(p.get("score") or 0)))
        used += 1
        pos += w * sum(1 for x in _POS if x in low)
        neg += w * sum(1 for x in _NEG if x in low)
    if used < 3 or pos + neg == 0:
        return None
    share = pos / (pos + neg)
    return ("positive" if share >= 0.65 else "negative" if share <= 0.4 else "mixed"), used


def _cached(con, key: str):
    r = con.execute("SELECT * FROM reviews WHERE key=? AND at>?", (key, time.time() - REVIEW_TTL)).fetchone()
    return r


def review_info_for(o: Offer) -> dict:
    """{'rating','count','reddit','rposts'} for one offer (None where unknown). Uses a 7-day cache."""
    con = db()
    info = {"rating": None, "count": 0, "reddit": None, "rposts": 0, "pr": None}
    ukey = "u:" + o.url
    row = _cached(con, ukey)
    if row is not None:
        info["rating"], info["count"] = row["rating"], row["count"] or 0
    elif o.source != "ozb":
        rating = None
        try:
            rating = parse_rating(fetch(o.url, timeout=(4, 7)))
        except FetchError:
            pass
        info["rating"], info["count"] = (rating or (None, 0))
        con.execute("INSERT OR REPLACE INTO reviews(key,rating,count,at) VALUES(?,?,?,?)",
                    (ukey, info["rating"], info["count"], time.time()))
        con.commit()
    q = keywords_from_title(o.title)
    if q:
        pkey = "p:" + norm(q)
        row = _cached(con, pkey)
        if row is not None:
            info["pr"] = (row["rating"], row["count"] or 0) if row["rating"] else None
        else:
            pr = productreview_rating(q)
            con.execute("INSERT OR REPLACE INTO reviews(key,rating,count,at) VALUES(?,?,?,?)",
                        (pkey, pr[0] if pr else None, pr[1] if pr else 0, time.time()))
            con.commit()
            info["pr"] = pr
        rkey = "r:" + norm(q)
        row = _cached(con, rkey)
        if row is not None:
            info["reddit"], info["rposts"] = row["label"], row["n"] or 0
        else:
            res = reddit_sentiment(q)
            if _REDDIT["until"] <= time.time():        # only remember real answers, not "Reddit said no"
                con.execute("INSERT OR REPLACE INTO reviews(key,label,n,at) VALUES(?,?,?,?)",
                            (rkey, res[0] if res else None, res[1] if res else 0, time.time()))
                con.commit()
            if res:
                info["reddit"], info["rposts"] = res
    return info


def review_verdict(info: dict | None, price: float | None = None, typical: float | None = None) -> tuple[str | None, str]:
    """(tone, short text) tone: good | ok | poor | None (nothing known)."""
    if not info:
        return None, ""
    r, n, lab = info.get("rating"), info.get("count") or 0, info.get("reddit")
    pr = info.get("pr")
    parts = []
    if r:
        parts.append(f"\u2605 {r:.1f}" + (f" ({n:,})" if n else ""))
    elif pr:
        r, n = pr
        parts.append(f"ProductReview \u2605 {r:.1f}" + (f" ({n:,})" if n else ""))
    if lab:
        parts.append(f"Reddit {lab}")
    if not parts:
        return None, ""
    bad = (r is not None and n >= 5 and r < 3.5) or lab == "negative"
    good = (r is not None and n >= 5 and r >= 4.2 and lab != "negative") or (lab == "positive" and (r is None or r >= 3.8))
    tone = "poor" if bad else "good" if good else "ok"
    if tone == "poor" and price and typical and price >= 1.2 * typical:
        parts.append("pricey for what it is")
    elif tone == "poor":
        parts.insert(0, "Poor reviews")
    return tone, "  \u00b7  ".join(parts)


def passes_reviews(mode: str, info: dict | None, unknown_ok: bool) -> bool:
    if mode in ("Off", "Show ratings"):
        return True
    tone, _ = review_verdict(info)
    if mode == "Hide poor reviews":
        return tone != "poor"
    if mode == "Only 4 stars and up":
        if not info or tone is None:
            return unknown_ok
        r, n = info.get("rating"), info.get("count") or 0
        if r is None and info.get("pr"):
            r, n = info["pr"]
        return (r is not None and r >= 4.0 and n >= 3) or (r is None and info.get("reddit") == "positive")
    return True


def check_reviews(offers: list[Offer], cb=None, limit: int = 30, workers: int = 6):
    """Look up ratings for the first `limit` distinct offers. cb(offer, info) is called as each one finishes."""
    seen, todo = set(), []
    for o in offers:
        if o.url not in seen:
            seen.add(o.url)
            todo.append(o)
        if len(todo) >= limit:
            break

    def one(o):
        try:
            info = review_info_for(o)
        except Exception:  # noqa: BLE001
            info = {"rating": None, "count": 0, "reddit": None, "rposts": 0}
        if cb:
            cb(o, info)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))


# --------------------------------------------------------------------------- #
# Price history for everything we see, "was price" sanity check
# --------------------------------------------------------------------------- #
def record_seen(con, offers: list[Offer], now: float | None = None):
    now = now or time.time()
    urls = [o.url for o in offers]
    last: dict[str, tuple[float, float]] = {}
    for i in range(0, len(urls), 400):
        chunk = urls[i:i + 400]
        q = ("SELECT s.url, s.price, s.at FROM seen s JOIN (SELECT url, MAX(at) m FROM seen WHERE url IN (%s) GROUP BY url) t "
             "ON s.url=t.url AND s.at=t.m" % ",".join("?" * len(chunk)))
        for r in con.execute(q, chunk):
            last[r["url"]] = (r["price"], r["at"])
    rows = []
    for o in offers:
        prev = last.get(o.url)
        if prev is None or abs(prev[0] - o.price) > 0.004 or now - prev[1] > 20 * 3600:
            rows.append((o.url, o.price, now))
    if rows:
        con.executemany("INSERT INTO seen(url,price,at) VALUES(?,?,?)", rows)
        con.commit()


def history_stats(con, urls, days: int = 180) -> dict:
    """{url: {'min','max','n','span','median'}} from every price we have seen for these pages."""
    urls, out, since = list(urls), {}, time.time() - days * 86400
    for i in range(0, len(urls), 400):
        chunk = urls[i:i + 400]
        q = "SELECT url, price, at FROM seen WHERE at>? AND url IN (%s)" % ",".join("?" * len(chunk))
        rows: dict[str, list] = {}
        for r in con.execute(q, (since, *chunk)):
            rows.setdefault(r["url"], []).append((r["price"], r["at"]))
        for u, lst in rows.items():
            ps = sorted(p for p, _ in lst)
            ts = [t for _, t in lst]
            min_at = max(t for p, t in lst if p == ps[0])
            out[u] = {"min": ps[0], "min_at": min_at, "max": ps[-1], "n": len(lst), "span": (max(ts) - min(ts)) / 86400,
                      "median": ps[len(ps) // 2], "series": [p for p, _ in sorted(lst, key=lambda x: x[1])][-14:]}
    return out


def ago_text(ts: float, now: float | None = None) -> str:
    d = ((now or time.time()) - ts) / 86400
    if d < 1:
        return "today"
    if d < 14:
        return f"{int(d)} day{'s' if int(d) != 1 else ''} ago"
    if d < 60:
        return f"{int(d // 7)} weeks ago"
    return f"{int(d // 30)} months ago"


def low_line(o: Offer, st: dict | None, sym: str = "$") -> str:
    """'Seen as low as $389 (3 weeks ago)' for a page whose price we have recorded before, when it was lower then."""
    if not st or o.source == "ozb" or st["n"] < 3 or st["span"] < 2 or st["min"] >= o.price * 0.97:
        return ""
    return f"Seen as low as {money(sym, st['min'])} ({ago_text(st['min_at'])})"


def price_verdict(o: Offer, st: dict | None) -> tuple[str | None, str]:
    """('lowest' | 'inflated' | None, text) from what we've seen this page charge before."""
    if not st or o.source == "ozb":
        return None, ""
    if st["n"] >= 3 and st["span"] >= 2 and o.price <= st["min"] + 0.005 and st["max"] > o.price * 1.03:
        return "lowest", f"Lowest price seen in {max(3, round(st['span']))} days"
    if o.was_price and st["n"] >= 4 and st["span"] >= 7 and st["max"] <= o.price * 1.04:
        return "inflated", "Was price unverified - never seen higher"
    return None, ""


# --------------------------------------------------------------------------- #
# Same product at several stores, price-match hints, cashback
# --------------------------------------------------------------------------- #
def model_key(title: str) -> str | None:
    """'wh1000xm5|sony' style key when the title has a real model code (letters + digits), else None."""
    toks = _tokens(title)
    models = sorted({norm(t) for t in toks if any(c.isdigit() for c in t) and any(c.isalpha() for c in t)
                     and len(norm(t)) >= 4 and not re.fullmatch(r"\d+(?:gb|tb|mm|cm|hz|w|v|inch|in|k|mah|l|kg|g)", norm(t))})
    if not models:
        return None
    brand = next((norm(t) for t in toks if _is_brand(t)), "")
    return brand + "|" + "|".join(models[:2])


def group_offers(offers: list[Offer]) -> list[Offer]:
    """One entry per product: the cheapest listing, with `.others` = the same product at other stores."""
    groups: dict[str, list[Offer]] = {}
    out: list[tuple[int, Offer]] = []
    for idx, o in enumerate(offers):
        k = None if (o.accessory or o.used or o.source == "ozb") else model_key(o.title)
        o.others = []
        if k is None:
            out.append((idx, o))
        elif k in groups:
            groups[k].append(o)
        else:
            groups[k] = [o]
            out.append((idx, o))
    result = []
    for idx, o in out:
        k = None if (o.accessory or o.used or o.source == "ozb") else model_key(o.title)
        mem = groups.get(k) if k else None
        if mem and len(mem) > 1:
            same_store = {}
            for m in sorted(mem, key=lambda m: (m.oos, m.price)):
                same_store.setdefault(m.store, m)          # one listing per store
            lst = list(same_store.values())
            prim = lst[0]
            prim.others = lst[1:]
            result.append(prim)
        else:
            result.append(o)
    return result


PRICE_MATCH = {"Officeworks": "says it will beat a lower competitor price", "Bunnings": "says it will beat a lower competitor price",
               "JB Hi-Fi": "says it will match a lower price", "The Good Guys": "says it will match a lower price",
               "Harvey Norman": "says it will match a lower price", "Bing Lee": "says it will match a lower price",
               "Big W": "says it will match a lower price", "Target AU": "says it will match a lower price",
               "Kmart": "has a limited price-match policy", "Appliances Online": "says it will match a lower price"}


def price_match_hint(store: str) -> str | None:
    base = re.sub(r"^OzBargain:\s*", "", store)
    for k, v in PRICE_MATCH.items():
        if k.lower() in base.lower():
            return f"{k} {v} (check current terms and exclusions)"
    return None


def effective_price(price: float, cashback_pct: float) -> float:
    return price * (1 - max(0.0, min(cashback_pct, 50.0)) / 100)


def value_score(o: Offer, info: dict | None) -> float:
    """Lower sorts first: well-reviewed and cheap wins. Rating is pulled towards 3.5 when there are few reviews."""
    if not info or not (info.get("rating") or info.get("pr")):
        return 1e9 + o.price
    r, n = info.get("rating"), info.get("count") or 0
    if r is None:
        r, n = info["pr"]
    bayes = (r * n + 3.5 * 10) / (n + 10)
    return -((bayes - 2.5) / math.sqrt(max(o.price, 1.0)))


def productreview_rating(query: str) -> tuple[float, int] | None:
    """Best effort: ProductReview.com.au is the main Australian review site. Returns (rating, reviews) or None."""
    try:
        page = fetch("https://www.productreview.com.au/search?q=" + quote_plus(query), timeout=(4, 7))
        m = re.search(r'href=["\'](/listings/[a-z0-9\-]+)["\']', page)
        if not m:
            return None
        return parse_rating(fetch("https://www.productreview.com.au" + m.group(1), timeout=(4, 7)))
    except FetchError:
        return None


# --------------------------------------------------------------------------- #
# Reported listings, backups, export, run-at-startup, sale seasons
# --------------------------------------------------------------------------- #
def hidden_url_set(con) -> set[str]:
    return {r["url"] for r in con.execute("SELECT url FROM hidden_urls")}


def unhide_listing(con, url: str):
    con.execute("DELETE FROM hidden_urls WHERE url=?", (url,))
    con.commit()
    _HIDDEN_CACHE.clear() if "_HIDDEN_CACHE" in globals() else None


def hide_listing(con, o: Offer, correct: float | None = None):
    """The user says this listing's price is wrong: log it and stop showing it."""
    con.execute("INSERT OR REPLACE INTO hidden_urls(url,store,title,price,correct,at) VALUES(?,?,?,?,?,?)",
                (o.url, o.store, o.title, o.price, correct, time.time()))
    con.commit()


def export_csv(folder: str) -> list[str]:
    con = db()
    made = []
    for name, sql in (("watchlist.csv", "SELECT keywords,max_price,min_drop_pct,best_price,best_store,best_title,best_url FROM watchlist"),
                      ("price_history.csv", "SELECT url,price,datetime(at,'unixepoch','localtime') AS seen FROM seen ORDER BY at"),
                      ("alerts.csv", "SELECT keywords,title,store,price,reasons,datetime(sent_at,'unixepoch','localtime') AS sent FROM alerts ORDER BY sent_at"),
                      ("reported_prices.csv", "SELECT store,title,price,correct,url,datetime(at,'unixepoch','localtime') AS reported FROM hidden_urls")):
        rows = con.execute(sql).fetchall()
        path = os.path.join(folder, name)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if rows:
                w.writerow(rows[0].keys())
                w.writerows([tuple(r) for r in rows])
            else:
                w.writerow(["(nothing yet)"])
        made.append(path)
    return made


def backup_db(dest: str):
    con = db()
    out = sqlite3.connect(dest)
    with out:
        con.backup(out)
    out.close()


def restore_db(src: str) -> bool:
    """Replace the database with a backup (takes effect after a restart). False if the file isn't a Deals backup."""
    try:
        t = sqlite3.connect(src)
        names = {r[0] for r in t.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        t.close()
    except sqlite3.Error:
        return False
    if not {"watchlist", "stores", "settings"} <= names:
        return False
    try:                                           # keep the current database in case the restore was a mistake
        shutil.copyfile(str(DB_PATH), str(DB_PATH) + ".before-restore")
    except OSError:
        pass
    try:                                           # SQLite's own copy: safe even while Deals has the database open
        s_con, d_con = sqlite3.connect(src), sqlite3.connect(str(DB_PATH), timeout=30)
        with d_con:
            s_con.backup(d_con)
        s_con.close()
        d_con.close()
    except sqlite3.Error:
        return False
    global _SEEDED
    _SEEDED = False                                # re-check/upgrade the restored (maybe old) database on next open
    _DB_READY.clear()
    return True


def _autostart_file() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft/Windows/Start Menu/Programs/Startup/Deals.bat"
    if sys.platform == "darwin":
        return Path.home() / "Library/LaunchAgents/au.deals.app.plist"
    return Path.home() / ".config/autostart/deals.desktop"


def autostart_enabled() -> bool:
    return _autostart_file().exists()


def set_autostart(on: bool, script: str | None = None):
    """Start Deals (minimised) when you log in, so alerts keep working without you opening it."""
    f = _autostart_file()
    if not on:
        try:
            f.unlink()
        except FileNotFoundError:
            pass
        return
    script = script or str(Path(__file__).parent / "DealScraper.pyw")
    py = sys.executable
    f.parent.mkdir(parents=True, exist_ok=True)
    if FROZEN and sys.platform.startswith("win"):               # the packaged exe is the program itself
        f.write_text(f'@echo off\r\nstart "" "{py}" --minimized\r\n', encoding="utf-8")
    elif sys.platform.startswith("win"):
        pyw = py[:-10] + "pythonw.exe" if py.lower().endswith("python.exe") else py
        f.write_text(f'@echo off\r\ncd /d "{Path(script).parent}"\r\nstart "" "{pyw}" "{script}" --minimized\r\n', encoding="utf-8")
    elif sys.platform == "darwin":
        f.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>au.deals.app</string>
<key>ProgramArguments</key><array><string>{py}</string><string>{script}</string><string>--minimized</string></array>
<key>RunAtLoad</key><true/></dict></plist>
""", encoding="utf-8")
    else:
        f.write_text(f"[Desktop Entry]\nType=Application\nName=Deals\nExec={py} {script} --minimized\n", encoding="utf-8")


def sale_season(now: float | None = None) -> str | None:
    """A heads-up during the big Australian sale periods, when 'was' prices are most often inflated."""
    t = time.localtime(now or time.time())
    md = (t.tm_mon, t.tm_mday)
    if (11, 15) <= md <= (12, 3):
        return "Black Friday / Cyber Monday: 'was' prices are often inflated at this time of year. Trust the price-history line on each card."
    if md >= (12, 24) or md <= (1, 6):
        return "Boxing Day / New Year sales: check the price-history line on each card before trusting a 'was' price."
    if (6, 10) <= md <= (7, 5):
        return "End of financial year sales: check the price-history line on each card before trusting a 'was' price."
    return None


# --------------------------------------------------------------------------- #
# Typo-tolerant search: work out what the user meant
# --------------------------------------------------------------------------- #
VOCAB_EXTRA = set("""oled qled uhd hdmi earphones earphone headset webcam tripod gimbal adapter dock router modem extender mesh
powerboard lightbulb thermostat doorbell vacuum mop steamer iron kettle toaster blender juicer grill sandwich cooker slowcooker
freezer fridge dishwasher dryer washer heater cooler dehumidifier humidifier purifier mattress topper pillow quilt doona sheets
towels curtain blinds lamp chair desk bookshelf wardrobe trampoline scooter helmet skateboard bicycle treadmill rowing dumbbell
bench protein creatine vitamin shampoo conditioner perfume mascara lipstick skincare sunscreen razor trimmer shaver toothbrush
nappies wipes stroller carseat highchair lego puzzle boardgame playstation xbox nintendo controller keyboard monitor laptop
tablet smartphone television projector printer scanner speaker soundbar subwoofer turntable microphone amplifier camera lens
drone smartwatch bracelet earbuds airpods macbook chromebook notebook ultrabook gaming console wireless bluetooth portable
electric cordless rechargeable waterproof stainless""".split())
VOCAB_EXTRA |= set("""television monitors laptops notebooks computer computers desktop keyboard keyboards mouse mice headphones
earbuds speakers soundbar refrigerator refrigerators fridge freezer dishwasher dishwashers washing machine dryer microwave
oven cooktop rangehood airfryer fryer blender toaster kettle coffee espresso grinder vacuum cleaner robot mattress pillow
bedding furniture sofa couch recliner wardrobe drawers bookcase treadmill dumbbells exercise bicycle scooter helmet camping
tent sleeping backpack luggage suitcase sunglasses watch watches jewellery necklace bracelet perfume fragrance cologne
skincare moisturiser sunscreen shampoo toothbrush electric shaver trimmer straightener hairdryer hair dryer drill drills
grinder sander chainsaw lawnmower mower trimmer whipper snipper blower pressure washer generator ladder toolbox workbench
battery batteries charger charging cable cables adapter powerbank storage drive harddrive flash memory graphics processor
motherboard router modem wifi network switch printer toner cartridge scanner projector screen webcam microphone gaming
console controller playstation xbox nintendo switch steam deck headset chair desk lego puzzle trampoline playset pram
stroller carseat nappies formula toys dolls figures bluetooth wireless wired portable cordless rechargeable waterproof
smart android iphone ipad macbook galaxy pixel airpods apple samsung sony panasonic philips bosch dyson miele electrolux
breville delonghi kenwood tefal sunbeam logitech razer corsair asus acer lenovo huawei xiaomi oppo nokia motorola garmin
fitbit gopro canon nikon fujifilm olympus sigma tamron anker belkin netgear tplink ubiquiti synology seagate western
digital kingston sandisk crucial nvidia radeon intel ryzen thermaltake cooler master noctua""".split())
_VOCAB_CACHE: dict = {"at": 0.0, "words": {}}


def learn_vocab(con, offers: list[Offer]):
    """Remember the product words shops use, so spelling fixes know about them."""
    words: dict[str, int] = {}
    for o in offers:
        for w in set(re.findall(r"[a-z]{4,}", o.title.lower())):
            words[w] = words.get(w, 0) + 1
    if words:
        con.executemany("INSERT INTO vocab(word,n) VALUES(?,?) ON CONFLICT(word) DO UPDATE SET n=n+excluded.n",
                        list(words.items()))
        con.commit()


def _vocabulary(con) -> dict[str, int]:
    """word -> weight (higher = more trusted)."""
    now = time.time()
    if now - _VOCAB_CACHE["at"] < 60 and _VOCAB_CACHE["words"]:
        return _VOCAB_CACHE["words"]
    v: dict[str, int] = {}
    for w in VOCAB_EXTRA:
        v[w] = 3
    for w in WORD_CATS:
        v[w] = 5
    for w in list(SYNONYMS) + [x for xs in SYNONYMS.values() for x in xs]:
        v.setdefault(norm(w), 3)
    for b in list(BRANDS) + list(BRAND_ALIASES):
        v[norm(b)] = 8
    try:
        for r in con.execute("SELECT word, n FROM vocab WHERE n>=3 ORDER BY n DESC LIMIT 8000"):
            v[r["word"]] = max(v.get(r["word"], 0), min(r["n"], 20))
        for r in con.execute("SELECT keywords FROM watchlist"):
            for w in re.findall(r"[a-z]{4,}", r["keywords"].lower()):
                v[w] = max(v.get(w, 0), 10)
    except sqlite3.Error:
        pass
    _VOCAB_CACHE.update(at=now, words=v)
    return v


def _dl(a: str, b: str, limit: int) -> int:
    """Edit distance counting a swap of two neighbouring letters as one mistake (so 'samsnug' is 1 away from 'samsung')."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


def _fix_word(w: str, vocab: dict[str, int], aggressive: bool) -> str | None:
    if len(w) < 4 or w in vocab or w.rstrip("s") in vocab or w + "s" in vocab or w.endswith("es") and w[:-2] in vocab:
        return None
    limit = 2 if (len(w) >= 7 or aggressive) else 1
    best, key = None, None
    for cand, wt in vocab.items():
        if abs(len(cand) - len(w)) > limit or len(cand) < 4 or (len(w) == 4 and wt < 3):
            continue
        d = _dl(w, cand, limit)
        if d > limit or (d == 2 and cand[0] != w[0]):
            continue
        k = (d, -wt)
        if key is None or k < key:
            best, key = cand, k
    return best


def correct_query(text: str, aggressive: bool = False) -> tuple[str, list[tuple[str, str]]]:
    """Fix likely typos in a search ('samsnug galxy' -> 'samsung galaxy', 'play station' -> 'playstation').
    Model numbers, excluded words and anything we don't recognise are left alone. Returns (text, [(was, now)])."""
    inc, exc = parse_keywords(text)
    if not inc:
        return text, []
    vocab = _vocabulary(db())
    changes: list[tuple[str, str]] = []
    out: list[str] = []
    i = 0
    while i < len(inc):
        tok = inc[i]
        low = re.sub(r"[^a-z]", "", tok.lower())
        pure = tok.isalpha()
        if pure and i + 1 < len(inc) and inc[i + 1].isalpha():      # 'play station' -> 'playstation'
            joined = (tok + inc[i + 1]).lower()
            if joined in VOCAB_EXTRA or (joined in vocab and tok.lower() not in vocab and inc[i + 1].lower() not in vocab):
                changes.append((f"{tok} {inc[i + 1]}", joined))
                out.append(joined)
                i += 2
                continue
        if pure and " " not in tok:
            fixed = _fix_word(low, vocab, aggressive)
            if fixed and fixed != low:
                changes.append((tok, fixed))
                tok = fixed
        out.append(tok)
        i += 1
    if not changes:
        return text, []
    q = lambda t: f'"{t}"' if " " in t else t
    return " ".join([q(t) for t in out] + ["-" + x for x in exc]), changes


# --------------------------------------------------------------------------- #
# Paste a product link: read it, then look for it everywhere else
# --------------------------------------------------------------------------- #
def did_you_mean(query: str, words: dict[str, int]) -> str | None:
    """When a search finds little: the shops' own search often still returns products for a misspelled word
    (they match loosely, we filter strictly). Look at the words in those listings and swap in the closest one."""
    if not words:
        return None
    inc, exc = parse_keywords(query)
    vocab = _vocabulary(db())
    out, changed = [], False
    for tok in inc:
        low = tok.lower()
        if not tok.isalpha() or len(low) < 4 or low in words or low + "s" in words or low.rstrip("s") in words:
            out.append(tok)
            continue
        limit = 2 if len(low) >= 5 else 1
        best, key = None, None
        for cand, n in words.items():
            if abs(len(cand) - len(low)) > limit or len(cand) < 4:
                continue
            d = _dl(low, cand, limit)
            if d > limit or (d == 2 and cand[0] != low[0]):
                continue
            k = (d, -n - (3 if cand in vocab else 0))
            if key is None or k < key:
                best, key = cand, k
        if best and best != low and words[best] >= 2:
            out.append(best)
            changed = True
        else:
            out.append(tok)
    if not changed:
        return None
    q = lambda t: f'"{t}"' if " " in t else t
    return " ".join([q(t) for t in out] + ["-" + x for x in exc])


def is_url(text: str) -> bool:
    return bool(re.match(r"(?i)^\s*https?://\S+\s*$", text or ""))


def _store_name_for(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for lst in CATALOG.values():
        for name, tpl in lst:
            h = urlparse(tpl.replace("{query}", "x")).netloc.lower().removeprefix("www.")
            if h and (h == host or host.endswith("." + h) or h.endswith("." + host)):
                return name
    return host


def _product_node(n):
    if isinstance(n, list):
        for x in n:
            r = _product_node(x)
            if r:
                return r
    elif isinstance(n, dict):
        t = n.get("@type")
        if "Product" in (t if isinstance(t, list) else [t]) and n.get("name"):
            return n
        for v in n.values():
            if isinstance(v, (dict, list)):
                r = _product_node(v)
                if r:
                    return r
    return None


_GTIN_RE = re.compile(r'"(?:gtin\d*|ean|upc|barcode|isbn)"\s*:\s*"?(\d{8,14})', re.I)
_MPN_RE = re.compile(r'"mpn"\s*:\s*"([^"]{3,40})"', re.I)
_ITEMPROP_RE = re.compile(r'itemprop=["\'](gtin\d*|mpn)["\'][^>]*?content=["\']([^"\']{3,40})["\']', re.I)


def page_codes(page: str) -> dict:
    """Barcodes (GTIN/EAN/UPC) and manufacturer part numbers found in a product page's markup."""
    gt, mp = set(), set()
    for m in _GTIN_RE.finditer(page):
        gt.add(m.group(1).lstrip("0"))
    for m in _MPN_RE.finditer(page):
        mp.add(norm(m.group(1)))
    for kind, val in _ITEMPROP_RE.findall(page):
        if kind.lower().startswith("gtin"):
            if val.strip().isdigit():
                gt.add(val.strip().lstrip("0"))
        else:
            mp.add(norm(val))
    return {"gtin": {g for g in gt if len(g) >= 8}, "mpn": {m for m in mp if len(m) >= 4}}


def same_product(a: dict, b: dict) -> str:
    """'exact' (shared barcode or part number), 'different' (both have codes and they disagree) or '' (can't tell)."""
    if a["gtin"] and b["gtin"]:
        return "exact" if a["gtin"] & b["gtin"] else "different"
    if a["mpn"] and b["mpn"]:
        if a["mpn"] & b["mpn"] or any(x in y or y in x for x in a["mpn"] for y in b["mpn"]):
            return "exact"
        return "different"
    return ""


def match_link_offers(info: dict, offers: list[Offer], limit: int = 10, budget: float = 14.0) -> int:
    """Pasted-link search: confirm which results really are the same product. Uses the part number in the
    result's title where it has one, otherwise opens the cheapest few result pages and compares barcodes /
    part numbers. Sets Offer.match and returns how many were found to be a different model."""
    mine = info.get("codes") or {"gtin": set(), "mpn": set()}
    mpns = {m for m in mine["mpn"] if len(m) >= 5}
    cands = sorted((o for o in offers if o.source == "store" and not o.accessory and o.score >= 30), key=lambda o: o.price)
    todo = []
    for o in cands[:limit * 2]:
        t = norm(o.title)
        if any(m in t for m in mpns):
            o.match = "exact"
        elif len(todo) < limit and (mine["gtin"] or mine["mpn"]):
            todo.append(o)
    if todo:
        def look(o):
            try:
                return o, page_codes(fetch(o.url, timeout=(4, 6)))
            except Exception:  # noqa: BLE001
                return o, None
        ex = ThreadPoolExecutor(max_workers=4)
        futs = [ex.submit(look, o) for o in todo]
        try:
            for fut in as_completed(futs, timeout=budget):
                o, codes = fut.result()
                if codes:
                    o.match = same_product(mine, codes)
        except Exception:  # noqa: BLE001
            pass
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
    return sum(1 for o in offers if o.match == "different")


def parse_product_page(page: str, url: str) -> dict:
    """Best-effort: {'title','price','was','brand','model','image'} from a product page."""
    soup = make_soup(page)
    info = {"title": None, "price": None, "was": None, "brand": None, "model": None, "image": None,
            "url": url, "store": _store_name_for(url), "codes": page_codes(page)}
    node = None
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            node = _product_node(json.loads(tag.get_text()))
        except (json.JSONDecodeError, TypeError):
            node = None
        if node:
            break
    if node:
        info["title"] = str(node["name"]).strip()
        b = node.get("brand")
        info["brand"] = (b.get("name") if isinstance(b, dict) else b) if b else None
        info["model"] = node.get("mpn") or node.get("model") if isinstance(node.get("model"), str) or node.get("mpn") else None
        info["image"] = _first_image(node.get("image"), url)
        offers = node.get("offers") or []
        for o in offers if isinstance(offers, list) else [offers]:
            if isinstance(o, dict):
                v = parse_price(str(o.get("price", o.get("lowPrice"))) if o.get("price", o.get("lowPrice")) is not None else None)
                if v:
                    info["price"] = v
                    break
    if not info["title"]:
        m = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
        h1 = soup.find("h1")
        info["title"] = ((m.get("content") if m else None) or (h1.get_text(" ", strip=True) if h1 else None)
                         or (soup.title.get_text(" ", strip=True) if soup.title else None))
        if info["title"]:
            info["title"] = re.split(r"\s[|\u2013\u2014-]\s(?=[A-Z])", info["title"])[0].strip()
    if not info["image"]:
        m = soup.find("meta", property="og:image")
        info["image"] = urljoin(url, m["content"]) if m and m.get("content") else None
    if not info["price"]:
        for prop in ("product:price:amount", "og:price:amount", "twitter:data1"):
            m = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            v = parse_price(m.get("content")) if m and m.get("content") else None
            if v:
                info["price"] = v
                break
    if not info["price"]:
        h1 = soup.find("h1")
        node2 = h1
        for _ in range(5):                              # the price block sits near the product heading
            if node2 is None or node2.parent is None or node2.name in ("body", "html"):
                break
            node2 = node2.parent
            sp, sw = _structured_price(node2)
            if sp:
                info["price"], info["was"] = sp, sw
                break
            txt = _capped_text(node2, 1500)
            vals = _pick_prices(txt) if txt else []
            if vals:
                info["price"] = vals[0]
                info["was"] = vals[-1] if len(vals) > 1 and vals[-1] > vals[0] * 1.02 else None
                break
    return info


def compact_query(info: dict) -> str:
    """A search that other shops will match: brand + model code + product type (not the whole marketing title)."""
    title = info.get("title") or ""
    toks = _tokens(title)
    models = []
    for t in toks:
        n = norm(t)
        if any(c.isdigit() for c in t) and any(c.isalpha() for c in t) and len(n) >= 4 and n not in models \
                and not re.fullmatch(r"\d+(?:gb|tb|mm|cm|hz|w|v|inch|in|k|mah|l|kg|g)", n):
            models.append(n if "-" not in t else t)
    mpn = info.get("model")
    if mpn and isinstance(mpn, str) and 4 <= len(mpn) <= 24 and norm(mpn) not in [norm(m) for m in models]:
        models.append(mpn)
    brand = info.get("brand") or next((t for t in toks if _is_brand(t)), "")
    types = _type_words(title)[:1]
    if models:
        return " ".join(x for x in [brand, *models[:2], *types] if x).strip()
    return keywords_from_title(title)


def product_from_url(url: str, cfg: dict | None = None) -> dict:
    """Read a product page and work out what it is. Raises FetchError when the page can't be read."""
    cfg = cfg or {}
    use_b = browser_wanted(cfg)
    rendered = False
    try:
        page = fetch(url, timeout=(6, 10))
    except FetchError as e:
        if e.kind != "blocked" or not use_b:
            raise
        page, rendered = BROWSER.render(url), True
    info = parse_product_page(page, url)
    if (not info["title"] or not info["price"]) and use_b and not rendered:
        try:
            info2 = parse_product_page(BROWSER.render(url), url)
            info = {**info, **{k: v for k, v in info2.items() if v}}
        except FetchError:
            pass
    if not info["title"]:
        raise FetchError("error", "couldn't find a product on that page")
    info["query"] = compact_query(info)
    return info
