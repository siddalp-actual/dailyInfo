#!/usr/bin/env python

import requests
import re
from bs4 import BeautifulSoup
import gkeepapi
import datetime
import numpy as np
import pandas as pd
import sys
import io
import traceback
import gkeepSecrets

printOnly = False

keepAccess = gkeepapi.Keep()
try:
    keepAccess.login(gkeepSecrets.mySecrets.app_user, gkeepSecrets.mySecrets.app_pw)
except Exception as err:
    print(err)
    print("gKeep login failure, using print only")
    printOnly = True


sys.path.append("../googledocs")
import gdriveFile as gf
import gdocHelper as gh

access = gf.gdriveAccess()
# keepAccess.load(access.credentials)
# outGdoc = gf.gdriveFile.gdfFromId(gkeepSecrets.mySecrets.TESTDOCID, access, docType='document')
outGdoc = gf.gdriveFile.gdfFromId(
    gkeepSecrets.mySecrets.TODAYDOCID, access, docType="document"
)
gh.GdocHelper.assertIsDoc(outGdoc)  # upgrade to a gdocHelper object
                                    # also has the side-effect of parsing the
                                    # document to create an 'outline' index


class ExchangeRate(object):
    url = "https://finance.yahoo.com/quote/"
    url = "https://www.bankofengland.co.uk/boeapps/database/Rates.asp?into=GBP"
    fakeUserAgent = "Whatever!"
    dateMatch = re.compile("\d{1,2} \w{3} \d{4}")

    def __init__(self):
        self.rates = {}
        self.url = ExchangeRate.url  # + f'{self.currency}=X'
        print(self.url)

    def calcHiLo(self, c):
        stats = {}
        rate = float(c[1].text.strip())
        stats["today"] = rate
        yearHi = float(c[2].text.strip())
        yearLo = float(c[3].text.strip())
        stats["yearHi"] = yearHi
        stats["yearLo"] = yearLo
        print(f"today: {rate} hi: {yearHi} lo: {yearLo}")
        diff = yearHi - yearLo
        diffToday = yearHi - rate
        prop = diffToday / diff * 100  # wouldn't want to sell dollars at highest rate
        # print(f"closeness {100 - prop}")
        stats["sellRecommend"] = prop
        return stats

    def getRates(self):
        sendHeaders = {"user-agent": ExchangeRate.fakeUserAgent}
        with requests.session() as requests_session:
            r = requests_session.get(self.url, headers=sendHeaders)
            print("<-Get():", r.status_code)
            # print(r.content)
            c = BeautifulSoup(r.content, features="lxml")
            rateTable = c.find("table")
            rows = rateTable.find_all("tr")
            for row in rows:
                # print(row)
                cells = row.find_all("td")
                if len(cells) > 0:
                    currency = cells[0].text.strip()
                    if currency == "Euro":
                        self.rates["GBPEUR"] = self.calcHiLo(cells)
                    if currency == "US Dollar":
                        self.rates["GBPUSD"] = self.calcHiLo(cells)
                else:
                    # the thead row has lots of \r \t formatting chars,
                    # so just parse out the date of the data
                    # print(repr(row.text))
                    matchObj = ExchangeRate.dateMatch.search(row.text)
                    if matchObj:
                        self.rates["date"] = matchObj.group(0)
                        print(matchObj.group(0))
        return self


def runMileage(dates):
    """
    dates is a list containing inclusive start and end
    """

    def shoeName(s):
        """
        Evaluates the row and returns a shoe name
        we have a prefix: old, new
        and suffix: road, xc
        """
        # print(s.name)
        import re

        matchobj = re.search(r"xc", s["Remarks"])
        if matchobj:
            sup = "XC"
            if s.name < pd.to_datetime("2021-02-26"):
                pre = "old"
            else:
                pre = "new"
        else:
            sup = "Road"
            if s.name < pd.to_datetime("2021-08-02"):
                pre = "old"
            else:
                pre = "new"
        return pre + sup

    sys.path.append("../googledocs")
    import gdriveFile as gf
    import shoe_sheet

    # yearStr = str(datetime.datetime.now().year)
    if dates[0].year != dates[1].year:
        # last week of year, special processing
        nowYear = str(datetime.datetime.now().year)
        if nowYear == str(dates[0].year) or datetime.datetime.now().day == 1:
            yearStr = str(dates[0].year)
        else:
            yearStr = str(dates[1].year)
    else:
        yearStr = str(dates[1].year)  # the year we're moving into

    print(f"working with year {yearStr}")

    start = yearStr + "-01-01"  # first Jan
    end = yearStr + "-12-31"  # end Dec

    nameQuery = "running log"
    searchString = "name contains '{}'".format(nameQuery)

    # print('searching for "{}"'.format(searchString))

    access = gf.gdriveAccess()
    gdoc = gf.gdriveFile.findDriveFile(access, searchString)

    # gdoc.showFileInfo()

    gdf = gdoc.toDataFrame(usecols=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9])

    gdfs = gdf[yearStr]  # only interested in the sheet named for the year
    gdfs.index = pd.to_datetime(
        gdfs.iloc[:, 0], dayfirst=True
    )  # assume zeroth column has date
    gdfs.drop("Date", axis=1, inplace=True)
    cn = "Distance miles"

    # anything in the miles column, that doesn't look like a decimal,
    # get's turned into NaN, and then 0
    gdfs[cn].replace(r"(?![\.0-9]+)", np.nan, regex=True, inplace=True)
    gdfs[cn].fillna(0, inplace=True)  # blanks / nulls etc set to 0
    # and the 'km' column to cope with skeleton formula
    gdfs["km"].replace(r"(?![\.0-9]+)", 0, regex=True, inplace=True)

    gdfs["tenk"] = gdfs["km"] >= 10
    tenks = len(gdfs[gdfs["tenk"] == True])
    if tenks == 0:
        mostRecent10kRank = 0
    else:
        gdfs["tenkrank"] = gdfs[gdfs["tenk"] == True]["Pace"].rank(method="max")
        # display(gdfs[gdfs['tenk'] == True])
        mostRecent10kRank = gdfs[gdfs["tenk"] == True]["tenkrank"].tail(1)
    print(gdfs.columns)

    # Now the document is cached, look at the bottom left and decide
    # whether to add some skeleton entries
    lr = gdoc.lastRow[yearStr]
    bottomLeftCell = gdfs.iloc[lr - 2, 0]  # -1 title, -1 0 base in df
    print("bottom left cell :", bottomLeftCell, ":")
    if bottomLeftCell == "":  # 0 date
        pass
    else:
        nr = lr + 1  # row number for new row
        gdoc.addData(
            "D",
            nr,
            [["=E{}/'2017'!$K$2".format(nr)]],
            sheet=yearStr,
            growSheet=True,
        )
        gdoc.addData(
            "G",
            nr,
            [["=C{}/D{}".format(nr, nr), "=C{}/E{}".format(nr, nr)]],
            sheet=yearStr,
        )

    weekSt = dates[0].strftime("%Y-%m-%d")
    weekNd = dates[1].strftime("%Y-%m-%d")
    print("week {}-{}".format(weekSt, weekNd))

    thisWeek = gdfs[(gdfs.index >= weekSt) & (gdfs.index <= weekNd)].copy()

    shoes = shoe_sheet.ShoeManager(gdf["Shoes"], handle=gdoc)
    shoe_runner = shoe_sheet.ShoeTracker(shoes, year=int(yearStr))
    gdfs["shoe"] = gdfs.apply(shoe_runner.assign_names, axis="columns")
    # .map(
    #     shoe_runner.shoe_name_mapping
    # )  # astype("category")

    #
    # # Assign shoe names for grouping
    # gdfs["shoe"] = gdfs.apply(shoeName, axis="columns").astype("category")
    residual = {
        "ASICS-GT1000-9": {"name": "ASICS-GT1000-9", "prevYear": 324.6},
        "Merrell XC": {"name": "Merrell XC", "prevYear": 505},
        "ASICS-GT1000-8": {"name": "ASICS-GT1000-8", "prevYear": 312},
        "Koa XC": {"name": "Koa XC", "prevYear": 381},
        "Inov8 X-Talon": {"name": "Inov8 X-Talon", "prevYear": 0},
    }
    # The order of keys of residual matches alphabetic collating sequence of
    # NewRoad, NewXc, OldRoad, OldXc
    # gdfs['shoe'].cat.categories = residual.keys()

    adder = shoe_sheet.ShoeMileYears(shoes, 6)
    adder.load()

    s = gdfs.groupby(["shoe"])[cn].sum()

    miles = {}
    # print(gdfs.iloc[:, 4])
    print(gdfs.loc[:, cn])
    miles[cn] = gdfs[cn].sum()

    for k in s.keys():
        # miles[residual[k]["name"]] = s[k] + residual[k]["prevYear"]
        miles[k] = s[k] + adder.residual(int(yearStr), shoename=k)

    # XC shoes ran 192 miles in 2019, and were stolen in June 2020 after 332 miles
    # miles['XC '+cn] = xcShoesYellow[cn].sum() + 193 - 332  # miles by end '19
    # miles['Blue ASICS '+cn] = blueAsics[cn].sum() - xcShoesBlue[cn].sum() + 140 #  140 miles in '18
    # miles['Yellow ASICS '+cn] = yellowAsics[cn].sum() - xcShoesYellow[cn].sum() + 332  # 332 miles in '19
    miles["week" + cn] = thisWeek[cn].sum()
    miles["10k's"] = "{:} {:d}/{:d}".format(tenks, int(mostRecent10kRank), int(tenks))
    print(miles)
    return miles


def bikeMileage(dates):
    """
    dates is a list containing inclusive start and end
    """

    sys.path.append("../googledocs")
    import gdriveFile as gf

    graterName = "2017 Charge Grater"
    talonName = "2014 Giant Talon 29er"
    sheetNames = [talonName, graterName, "2021 Giant Escape"]

    yearStr = str(datetime.datetime.now().year)

    start = yearStr + "-01-01"  # first Jan
    end = yearStr + "-12-31"  # end Dec

    nameQuery = "bike mileage"
    searchString = "name contains '{}'".format(nameQuery)

    # print('searching for "{}"'.format(searchString))

    access = gf.gdriveAccess()
    gdoc = gf.gdriveFile.findDriveFile(access, searchString)

    # gdoc.showFileInfo()

    gdf = gdoc.toDataFrame(usecols=[0, 1, 2, 4])

    # I know the grater sheet has column names
    grater = gdf[graterName]  # .iloc[:,0:5]

    gdfs = {}  # selected version
    for s in sheetNames:
        print(s)
        print(gdf[s].head())
        # print(grater.columns)
        gdf[s].columns = grater.columns
        # print(gdf[s])
        gdf[s].index = pd.to_datetime(
            gdf[s].iloc[:, 0], dayfirst=True
        )  # assume zeroth column has date
        gdfs[s] = gdf[s][(gdf[s].index >= start) & (gdf[s].index <= end)].copy()
        gdfs[s].name = gdf[s].name
        gdfs[s].drop("Date", axis=1, inplace=True)
        # catenate the frame name on the column to avoid asymmetry of merge
        gdfs[s].rename(
            {col: "{}{}".format(col, gdfs[s].name) for col in gdfs[s].columns},
            axis="columns",
            inplace=True,
        )
        # print(gdfs[s])

    # Now the document is cached, look at the bottom left and decide
    # whether to add some skeleton entries
    for s in sheetNames:
        lr = gdoc.lastRow[s]
        if s != talonName:
            # has title
            bottomLeftCell = gdf[s].iloc[lr - 2, 0]  # -1 title, -1 0 base in df
        else:
            bottomLeftCell = gdf[s].iloc[lr - 1, 0]  # -1 0 base in df
        print("bottom left cell :", bottomLeftCell, ":")
        if bottomLeftCell == "":  # 0 date
            pass
        else:
            nr = lr + 1  # row number for new row
            gdoc.addData(
                "C", nr, [["=C{}+B{}".format(lr, nr)]], sheet=s, growSheet=True
            )

    # find this year's entries from different sheets
    thisYear = pd.DataFrame()
    for s in gdfs.keys():
        thisYear = thisYear.merge(
            gdfs[s],
            how="outer",
            sort=True,
            left_index=True,
            right_index=True,
            suffixes=["", ""],
        )
    print(thisYear.columns)

    weekSt = dates[0].strftime("%Y-%m-%d")
    weekNd = dates[1].strftime("%Y-%m-%d")
    print("week {}-{}".format(weekSt, weekNd))

    thisWeek = thisYear[(thisYear.index >= weekSt) & (thisYear.index <= weekNd)].copy()

    miles = {}
    for cn in thisYear.columns:
        if cn.startswith("Miles"):
            # replace non numeric with 0
            thisYear[cn].replace(r"(?![\.0-9]+)", 0, regex=True, inplace=True)
            miles[cn] = thisYear[cn].sum()
            miles["week" + cn] = thisWeek[cn].sum()
    return miles


def extractData(node):
    """
    node is a table,
    iterate through the rows finding sunrise, sunset, then the
    embedded table with tides
    """
    outS = ""
    for i, row in enumerate(node.find_all("tr")):
        if i in (0, 1):
            print(row.contents[1].string, row.contents[3].string)
            outS += row.contents[1].string + " "
            outS += row.contents[3].string
            outS += "\n"
        if i == 2:
            moonrise = row.contents[1].string + " " + row.contents[3].string
        if i == 5:
            for s in row.stripped_strings:
                print(s)
                outS += "\n" + s

    return (outS, moonrise)


def getImage(r_s):
    import shutil

    NAME = "meteogram.png"
    imgsrc = URL + "/" + NAME
    response = r_s.get(imgsrc, stream=True)
    with open(NAME, "wb") as out_file:
        shutil.copyfileobj(response.raw, out_file)


def update(note, content):
    now = datetime.datetime.now()
    note.title = "Today: {}\nUpdated: {}".format(now.date(), now.strftime("%H:%M:%S"))
    note.text = content


def usefulDate(today):
    weekSt = today - datetime.timedelta(days=today.weekday())
    weekNd = weekSt + datetime.timedelta(days=6)
    outStr = "\n"
    outStr += "Week number " + today.strftime("%V") + "\n"
    outStr += "start of week {} {}".format(weekSt.strftime("%a"), weekSt.date())
    outStr += "\n"
    outStr += "end   of week {} {}".format(weekNd.strftime("%a"), weekNd.date())
    outStr += "\n"
    return (outStr, weekSt.date(), weekNd.date())


def almanacData(today):
    URL = "http://southamptonweather.co.uk"
    r_s = requests.session()
    resp = r_s.get(URL)

    soup = BeautifulSoup(resp.content, features="lxml")
    try:
        # from the almanac table extract sunrise / moonrise times
        for s in soup.find_all("td", "data1"):
            # print(s)
            if s.string:
                m = re.match("Moonrise", s.string)  # a unique word in page
                if m:
                    (sun, moon) = extractData(s.parent.parent)  # the enclosing table
                    # print("matched...")

        p = sun
    except:
        p = "Failure extracting almanac info from web page"

    try:
        # find the moon phase image
        for s in soup.find_all("img", src=re.compile("moon", flags=re.IGNORECASE)):
            moon += " " + s["alt"]

        p += "\n" + moon
    except:
        p += "Failure extracting moon phase text"

    return p


if printOnly:
    pass
else:
    keepAccess.sync()
    gnotes = keepAccess.find(labels=[keepAccess.findLabel("AppUniq")])

today = datetime.datetime.now()
yesterday = today - datetime.timedelta(days=1)

p = almanacData(today)
p += "\n\n"

myStream = io.StringIO()
saveStdOut = sys.stdout

try:
    exchange = ExchangeRate().getRates()
    sys.stdout = myStream
    # capture this print for the note
    for x in ("GBPEUR", "GBPUSD"):
        print(
            "{:}: {:.2f} sell?: {:.0f}%".format(
                x,
                exchange.rates[x]["today"],
                exchange.rates[x]["sellRecommend"],
            )
        )
except:
    sys.stdout = myStream
    print("Failure getting exchange rates")
finally:
    sys.stdout = saveStdOut

p += myStream.getvalue()
myStream.close()
p += "\n\n"


# I run this early in the morning to web data for today, eg tide, moon
# but, the week I'm interested in for cycle and run distance is the one
# which contains yesterday
(text, mon, sun) = usefulDate(yesterday)

try:
    # Do the bike stuff
    miles = bikeMileage((mon, sun))
    totalYear = 0
    totalWeek = 0

    p += "{} Bike Mileage:\n".format(today.year)
    for k in miles:
        p += " {}: {}\n".format(k, miles[k])
        if k.startswith("week"):
            totalWeek += miles[k]
        else:
            totalYear += miles[k]
    p += "Total for week: {} year: {}\n".format(totalWeek, totalYear)
except:
    p += "Failure processing bike mileage"

try:
    # Do the running stuff
    miles = runMileage((mon, sun))
    totalYear = 0
    totalWeek = 0

    p += "\n{} Running Mileage:\n".format(today.year)
    for k in miles:
        print(miles[k])
        if type(miles[k]) == str:
            p += " {}: {}\n".format(k, miles[k])
        else:
            p += " {}: {:.1f}\n".format(k, miles[k])
except Exception as e:
    print(e)
    print(sys.exc_info())
    print(traceback.print_tb(sys.exc_info()[2]))
    p += "Failure processing running mileage"

(text, mon, sun) = usefulDate(today)
p += text

# getImage(r_s) can't yet work out how to put in a note :-(


def cleanOldEntry(doc):
    (dateStr, index) = doc.outline.findFirstDate()
    # print(f"cleanOld: found {dateStr} at index {index} of {len(doc.outline.headings)}")
    older = datetime.datetime.now() - datetime.timedelta(hours=72)
    while index < len(doc.outline.headings):
        # going to loop over the dated titles
        date = datetime.datetime.strptime(dateStr, "%a %d %b %Y")
        if date < older:  # want to delete it
            startPos = doc.outline.headings[index].startPos
            if index >= len(doc.outline.headings) - 1:
                endPos = doc.docExtent
            else:
                endPos = doc.outline.headings[index + 1].startPos
            # 'Invalid requests[0].deleteContentRange: The range cannot include
            # the newline character at the end of the segment.
            # So, we go to endPos - 1 
            # print(f"cleanOld: delete [{startPos}, {endPos - 1}]")
            doc.deleteText(startPos, endPos - 1)
            index -= 1  # backup an index, because we just deleted it
        else:
            # skip over the recent one we found and try again
            # print(f"cleanOld: skipping...")
            pass
        try:
            (dateStr, index) = doc.outline.findFirstDate(after=index)
            # print(f"cleanOld: found {dateStr} at index {index} of {len(doc.outline.headings)}")
        except Exception as e:
            return  # couldn't parse out a date so leave deletion


if printOnly:
    print(p)
    #                      %a = Wed, %d = 27, %b = May, %Y = 2020
    (dateStr, index)  = outGdoc.outline.findFirstDate()
    # findFirstDate returns the start of the section title line,
    # I want to backup before the preceding newline
    startPos = outGdoc.outline.headings[index].startPos - 1
    outGdoc.insertTextWithHeader(today.strftime("Update for %a %d %b %Y"), p, startPos)

    cleanOldEntry(outGdoc)
    # outGdoc.appendToDoc(today.strftime("Update for %a %d %b %Y"))
    # outGdoc.appendToDoc(p)
else:
    for i, n in enumerate(gnotes):
        if i == 0:
            update(n, p)
            # for c in n.collaborators.all():
            #    print(c)

    keepAccess.sync()
