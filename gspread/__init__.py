from xml.etree import ElementTree

from .httpsession import HTTPSession


AUTH_SERVER = 'https://www.google.com'
SPREADSHEETS_SERVER = 'spreadsheets.google.com'
ATOM_NS = 'http://www.w3.org/2005/Atom'
SPREADSHEET_NS = 'http://schemas.google.com/spreadsheets/2006'


def _ns(name):
    return '{%s}%s' % (ATOM_NS, name)

def _ns1(name):
    return '{%s}%s' % (SPREADSHEET_NS, name)


class Client(object):
    def __init__(self, auth, http_session=None):
        self.auth = auth

        if not http_session:
            self.session = HTTPSession()

    def _get_auth_token(self, content):
        for line in content.splitlines():
            if line.startswith('Auth='):
                return line[5:]
        return None

    def login(self):
        source = 'burnash-gspread-0.0.1'
        service = 'wise'

        data = {'Email': self.auth[0],
                'Passwd': self.auth[1],
                'accountType': 'HOSTED_OR_GOOGLE',
                'service': service,
                'source': source}

        url = AUTH_SERVER + '/accounts/ClientLogin'

        r = self.session.post(url, data)
        content = r.read()

        if r.code == 200:
            token = self._get_auth_token(content)
            auth_header = "GoogleLogin auth=%s" % token
            self.session.add_header('Authorization', auth_header)

        elif r.code == 403:
            if content.strip() == 'Error=BadAuthentication':
                raise Exception("Incorrect username or password")
            else:
                raise Exception("Unable to authenticate. %s code" % r.code)
        else:
            raise Exception("Unable to authenticate. %s code" % r.code)

    def get_spreadsheets_feed(self, visibility='private', projection='full'):
        uri = ('https://%s/feeds/spreadsheets/%s/%s'
            % (SPREADSHEETS_SERVER, visibility, projection))

        r = self.session.get(uri)
        return ElementTree.fromstring(r.read())

    def get_worksheets_feed(self, key, visibility='private', projection='full'):
        uri = ('https://%s/feeds/worksheets/%s/%s/%s'
            % (SPREADSHEETS_SERVER, key, visibility, projection))

        r = self.session.get(uri)
        return ElementTree.fromstring(r.read())

    def get_cells_feed(self, key, worksheet_key, cell=None,
                       visibility='private', projection='full'):
        uri = ('https://%s/feeds/cells/%s/%s/%s/%s'
            % (SPREADSHEETS_SERVER, key, worksheet_key, visibility, projection))

        if cell != None:
            uri = '%s/%s' % (uri, cell)

        r = self.session.get(uri)
        return ElementTree.fromstring(r.read())

    def put_cell(self, url, data):
        headers = {'Content-Type': 'application/atom+xml'}
        data = "<?xml version='1.0' encoding='UTF-8'?>%s" % data
        r = self.session.put(url, data, headers=headers)

        return ElementTree.fromstring(r.read())

    def open(self, name):
        feed = self.get_spreadsheets_feed()

        for elem in feed.findall(_ns('entry')):
            title = elem.find(_ns('title')).text
            if title.strip() == name:
                id_parts = elem.find(_ns('id')).text.split('/')
                key = id_parts[-1]
                return Spreadsheet(self, key)


class Spreadsheet(object):
    def __init__(self, client, key):
        self.client = client
        self.key = key
        self._sheet_list = []

    def sheet_by_name(self, sheet_name):
        pass

    def _fetch_sheets(self):
        feed = self.client.get_worksheets_feed(self.key)
        for elem in feed.findall(_ns('entry')):
            key = elem.find(_ns('id')).text.split('/')[-1]
            self._sheet_list.append(Worksheet(self, key))

    def worksheets(self):
        if not self._sheet_list:
            self._fetch_sheets()
        return self._sheet_list[:]

    def get_worksheet(self, sheet_index):
        if not self._sheet_list:
            self._fetch_sheets()
        return self._sheet_list[sheet_index]


class Worksheet(object):
    def __init__(self, spreadsheet, key):
        self.spreadsheet = spreadsheet
        self.client = spreadsheet.client
        self.key = key

    def row(self, rowx):
        pass

    def cell(self, rowx, colx):
        pass

    def _fetch_cells(self):
        feed = self.client.get_cells_feed(self.spreadsheet.key, self.key)
        cells_list = []
        for elem in feed.findall(_ns('entry')):
            c_elem = elem.find(_ns1('cell'))
            cells_list.append(Cell(self, c_elem.get('row'), c_elem.get('col'), c_elem.text))

        return cells_list

    def get_rows(self):
        cells = self._fetch_cells()

        rows = {}
        for cell in cells:
            rows.setdefault(int(cell.row), []).append(cell)

        rows_list = []
        for r in sorted(rows.keys()):
            rows_list.append(rows[r])

        simple_rows_list = []
        for r in rows_list:
            simple_row = []
            for c in r:
                simple_row.append(c.value)
            simple_rows_list.append(simple_row)

        return simple_rows_list

    def col_values(self, colx):
        cells_list = self._fetch_cells()

        cells = {}
        for cell in cells_list:
            if int(cell.col) == colx:
                cells[int(cell.row)] = cell

        last_index = max(cells.keys())
        vals = []
        for i in range(last_index):
            c = cells.get(i)
            vals.append(c.value if c else None)

        return vals

    def update_cell(self, rowx, colx, val):
        cell_addr = 'R%sC%s' % (rowx, colx)

        feed = self.client.get_cells_feed(self.spreadsheet.key, self.key, cell_addr)
        cell_elem = feed.find(_ns1('cell'))
        cell_elem.set('inputValue', val)
        edit_link = filter(lambda x: x.get('rel') == 'edit',
                feed.findall(_ns('link')))[0]
        uri = edit_link.get('href')

        self.client.put_cell(uri, ElementTree.tostring(feed))


class Cell(object):
    def __init__(self, worksheet, row, col, value):
        self.row = row
        self.col = col
        self.value = value