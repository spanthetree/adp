#!/usr/bin/env python

import argparse
import http.cookiejar
import getpass
import os
import sys
import time
import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse
from bs4 import BeautifulSoup

class PayCheckFetcher:
    paycheck_url = 'https://ipay.adp.com/iPay/private/listDoc.jsf'
    cj = None
    time_between_requests = 1
    last_request_time = 0

    def __init__(self, args):
        # why is this so verbose
        pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, 'http://agateway.adp.com', args.username, args.passwd)
        # need cookies so auth works properly
        self.cj = http.cookiejar.LWPCookieJar()
        o = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(pm), urllib.request.HTTPCookieProcessor(self.cj))
        urllib.request.install_opener(o)

        # make an intial request. we need to do this
        # as it updates our session cookie appropriately, so that
        # child frames know that this is the parent (they apparently
        # don't look at referrer)
        self.getResponse(url='https://ipay.adp.com/iPay/private/index.jsf')


    # given some data and a url, makes magical request for data using urllib2
    def getResponse(self, data=None, url=None):
        if (url == None):
            url = self.paycheck_url

        time_to_wait = self.time_between_requests - (time.time() - self.last_request_time)
        if (time_to_wait > 0):
            time.sleep(time_to_wait)

        # pretend to be chrome so the jsf renders as i expect
        ua = 'Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_4; en-US) AppleWebKit/534.13 (KHTML, like Gecko) Chrome/9.0.597.19 Safari/534.13'
        headers = { 'User-Agent' : ua }
        req = urllib.request.Request(url, data, headers)
        response = urllib.request.urlopen(req)
        return response

    # calls getResponse and throws it into soup. use prettify to view
    # the contents because adp has super ugly markup
    def getSoupResponse(self, data=None):
        soup = BeautifulSoup(self.getResponse(data))
        return soup

    # given soup, gets the statement form's inputs as a dictionary
    def getInputs(self, soup):
        # grab common form inputs
        form = soup.find('form', id='statement')
        inputs = form.findAll('input')
        values = {}
        for input in inputs:
            if (input['type'] == 'hidden'):
                values[input['name']] = input['value']

        # 2 is apparently w2s
        values['statement:changeStatementsType'] = 1

        return values

    # given soup, returns all the year ids (form data) in a dictionary
    # of year to year id
    def getAllYears(self, soup):
        # grab years available
        years = soup.find('span', id='statement:yearLinks').findAll('a')
        result = {}
        for year in years:
            if (year != None):
                result[year.string] = year['id']
        return result

    # like getAllYears but does the same thing for links to checks
    def getPayCheckData(self, soup):
        # grab paychecks present
        rows = soup.find('table', id='statement:checks').findAll('tr')
        result = {}
        for row in rows:
            checklink = row.find('a')
            if (checklink!= None):
                date_key = time.strftime('%Y-%m-%d', time.strptime(checklink.string, '%m/%d/%Y'))
                n = 0
                while date_key in result:
                    date_key = time.strftime('%Y-%m-%d-'+str(n), time.strptime(checklink.string, '%m/%d/%Y'))
                    n += 1
                result[date_key] = checklink['id']
        return result

    # downloads a file
    def downloadFile(self, args, url):
        path = os.path.abspath(args.localpath)
        print('downloading '+url+' --> '+path)
        fd = open(path, 'wb')
        response = self.getResponse(url = url)
        fd.write(response.read())
        fd.close()
        return

    # return us to the 'browse' view so navigating to the next year
    # works properly. (this is some jsf requirement)
    def returnToBrowse(self, soup):
        inputs = self.getInputs(soup)
        inputs['statement:done'] = 'statement:done'
        return self.getSoupResponse(urllib.parse.urlencode(inputs))

    # functions called from outside that does all the magic and saves
    # all the files
    def request(self, args):
        localpath = args.localpath
        soup = self.getSoupResponse()
        yeardata = sorted(list(self.getAllYears(soup).items()), reverse=True)
        for year, year_id in yeardata:
            print('processing '+year)
            inputs = self.getInputs(soup)
            inputs[year_id] = year_id
            year_soup = self.getSoupResponse(urllib.parse.urlencode(inputs))
            paychecks = sorted(list(self.getPayCheckData(year_soup).items()),
                    reverse=True)
            print(paychecks)
            print('found '+str(len(paychecks))+' checks in '+year)
            for datekey, date_id in paychecks:
                filename = datekey+'.pdf'
                if os.path.exists(os.path.abspath(filename)):
                    # note that this will break if adp adds a new check for
                    # the day you run this on. TODO: i should change the
                    # filename to a key with the check number
                    print('skipping (already downloaded): '+filename)
                    continue

                inputs = self.getInputs(year_soup)
                inputs[date_id] = date_id
                check_soup = self.getSoupResponse(urllib.parse.urlencode(inputs))
                check_url = 'https://ipay.adp.com'+check_soup.iframe['src']
                self.downloadFile(check_url, filename)

            # 'browse' back to the original page
            soup = self.returnToBrowse(year_soup)

def main():
    parser = argparse.ArgumentParser(
        description="Download ADP Pay Statements")
    parser.add_argument("username", help="ADP Username")
    parser.add_argument("--passwd", help="ADP Password",
        default=getpass.getpass())
    parser.add_argument("--localpath", help="Local Path for file download",
        default=".")

    args = parser.parse_args()
    if not os.path.isdir(args.localpath):
        raise RuntimeError("%s is not a directory" % args.localpath)

    fetcher = PayCheckFetcher(args)
    fetcher.request(args)


if __name__ == "__main__":
    main()
