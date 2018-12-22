#!/usr/bin/python
########################################################################################################################
#
#  Lemma Logic LLC
#  __________________
#
# Copyright 2018 Lemma Logic LLC
# All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
########################################################################################################################

from flask import Flask
from flask import Response
from flask import abort
from flask import flash
from flask import g
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from functools import wraps
import json, logging, logging.handlers, mysql.connector, os, string, sys, weakref, argparse, hashlib, uuid, schedule, atexit, collections
from mysql.connector import FieldType

parser = argparse.ArgumentParser()
parser.add_argument("--config", help="configuration file", type=str, default='config.json')
parser.add_argument("--loglevel", help="log level", type=str, default='INFO')
args = parser.parse_args()

logger = logging.getLogger('rest-datastore')
# logger.propagate = False
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger.setLevel(logging.DEBUG)
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO, formatter=formatter)
log = logging.getLogger('werkzeug')
if args.loglevel == "INFO":
    log.setLevel(logging.INFO)
elif args.loglevel == "DEBUG":
    log.setLevel(logging.DEBUG)

this_directory = os.path.abspath(os.path.dirname(__file__))
default_config = args.config
default_tasks_dir = os.path.join(this_directory, "tasks")

class User(object):
    def __init__(self, username, password):
        self._username = username
        self._password = password
    
    def getUsername(self):
        return self._username

    def authenticate(self, username, password):
        password = hashlib.sha224(password).hexdigest()
        result = username and password and self._username and self._password and self._username == username and self._password == password
        if not result:
            logger.warn("Unable to authenticate user: " + username)
        return result 

class MySqlConnection(object):
    def __init__(self, host, database, user, password, database_pool_size, pool_name):
        self._host = host
        self._database = database
        self._user = user
        self._password = password
        self._database_pool_size = database_pool_size
        self._pool_name = pool_name
        self._connection = self.createConnection()

    def createConnection(self):
        logger.info("Connecting to database: " + self._database)
        # Query cache is a problem.  If you don't commit after each query, you get stale data.  MySQL 8 removed query cache.
        # http://mysqlserverteam.com/mysql-8-0-retiring-support-for-the-query-cache/
        # https://stackoverflow.com/questions/21974169/how-to-disable-query-cache-with-mysql-connector
        # https://bugs.mysql.com/bug.php?id=42197
        return mysql.connector.connect(user=self._user,
                                                   password=self._password,
                                                   host=self._host,
                                                   pool_name = self._pool_name,
                                                   pool_size = self._database_pool_size,
                                                   database=self._database,
                                                   autocommit=True)
    def checkConnection(self):
        if weakref.ref(self._connection)() is None or not self._connection.is_connected():
            self._connection = self.createConnection()

    def close(self):
        self._connection.close()

    def getQueryColumnInfo(self, query, parameters):
        self.checkConnection()
        logger.debug("Executing query: %(query)s, using parameters: %(parameters)s" % {"query": query, "parameters": parameters})
        self._cursor = self._connection.cursor(buffered=True)
        self._cursor.execute(query.format( ** parameters))
        column_names = self._cursor.column_names
        column_types = self._cursor.description
        logger.debug("Returned column names: " + str(column_names))
        logger.debug("Returned column types: " + str(column_types))
        self._cursor.close()
        return column_names, column_types

    def execute(self, query, parameters, commit=False):
        self.checkConnection()
        try:
            logger.debug("Executing query: %(query)s, using parameters: %(parameters)s" % {"query": query, "parameters": parameters})
            self._cursor = self._connection.cursor()
            column_names = []
            rows = []
            for result in self._cursor.execute(query, parameters, multi=True):
                if result.with_rows:
                    column_names.extend(self._cursor.column_names)
                    logger.debug("Returned column names: " + str(column_names))
                    rows.extend(self._cursor.fetchall())
                    logger.debug("Returned column rows: " + str(rows))
            results = self.createResults(column_names, rows)
            if commit:
                logger.debug("Committing transaction...")
                self._connection.commit()
            logger.debug("Closing cursor...")
            self._cursor.close()
            logger.debug("Results: " + str(results))
            if not results:
                return True, None
            else:
                return True, results
        except mysql.connector.Error as err:
            logger.error("Query operation failed: {}".format(err))
            return False, None

    def executeMany(self, query, parameters, commit=False):
        self.checkConnection()
        try:
            logger.debug("Executing query: %(query)s, using parameters: %(parameters)s" % {"query": query, "parameters": parameters})
            self._cursor = self._connection.cursor()
            self._cursor.executemany(query, parameters)
            if commit:
                self._connection.commit()
            self._cursor.close()
            return True, None
        except mysql.connector.Error as err:
            logger.error("Query operation failed: {}".format(err))
            return False, None

    def createResults(self, column_names, rows):
        results = []
        for row in rows:
            nextItem = {}
            for item, column_name in zip(row, column_names):
                nextItem[str(column_name)] = item
            results.append(nextItem)
        return results


class JsonAdapter(object):
    @staticmethod
    def serialize(column_names, rows):
        jsonobject = []
        for row in rows:
            counter = 0
            rowdict = {}
            for column in row:
                rowdict[str(column_names[counter])] = column
                counter += 1
            jsonobject.append(rowdict)
        return json.dumps(jsonobject)

    @staticmethod
    def parse(json_str):
        if json_str:
            return json.loads(json_str, encoding="utf-8")
        else:
            return {}

class RestVerb(object):

    def __init__(self, usernames):
        self.parameters = frozenset()
        self.empty_parameters = {}
        self._usernames = usernames
        self.empty_response = None
        self._pusherEvents = []

    def isValidUser(self, username):
        return username and self._usernames and username in self._usernames

    @staticmethod
    def createInstanceFromConfig(verb_element):
        return_verb = RestVerb(verb_element["users"])
        if "description" in verb_element:
            return_verb.description = verb_element["description"]
        else:
            return_verb.description = "Not provided."
        if "commit" in verb_element:
            return_verb.commit = verb_element["commit"]
        else:
            return_verb.commit = False
        if "emptyResponse" in verb_element:
            return_verb.empty_response = verb_element["emptyResponse"]
        else:
            return_verb.empty_response = None
        if "pusherEvents" in verb_element:
            events = verb_element["pusherEvents"]
            for event in events:
                pass
                # return_verb._pusherEvents.add(PusherEvent(event["channel"], event["eventName", event["message"]]))
        if "query" in verb_element:
            return_verb.query = verb_element["query"]
            formatter = string.Formatter()
            params = []
            for i in formatter.parse(return_verb.query):
                if i[1] is None:
                    break
                else:
                    params.append(i[1])
                    return_verb.empty_parameters[i[1]] = "NULL"
            return_verb.parameters = frozenset(params)
        return return_verb

class RestEndpoint(object):
    def __init__(self, path):
        if (path):
            self._path = path.lower()
        else:
            raise Exception("Missing REST endpoint path.")
        self._format_adapter = JsonAdapter()

    def isValidUser(self, username, verb):
        return verb and username and verb.isValidUser(username)
    
    def isValidUserGet(self, username):
        return self.isValidUser(username, self.get_verb)
    
    def isValidUserPost(self, username):
        return self.isValidUser(username, self.post_verb)

    def isValidUserPut(self, username):
        return self.isValidUser(username, self.put_verb)

    def isValidUserDelete(self, username):
        return self.isValidUser(username, self.delete_verb)

    def setGet(self, get_verb):
        self.get_verb = get_verb

    def setPut(self, put_verb):
        self.put_verb = put_verb

    def setDelete(self, delete_verb):
        self.delete_verb = delete_verb

    def setPost(self, post_verb):
        self.post_verb = post_verb

    def merge(self, url_params = None, request_body = None, headers=None):
        merged = {}
        if url_params:
            for key, value in url_params.items():
                merged[key.upper()] = value
        if request_body:
            for key, value in request_body.items():
                merged[key.upper()] = value
        if headers:
            for key, value in headers.items():
                merged[key.upper()] = value
        return merged

    def executeGet(self, connection, url_params=None, request_body=None, headers=None):
        status, data = connection.execute(self.get_verb.query, self.merge(url_params, request_body, headers))
        return self.respond(self.get_verb, status, data)

    def executePut(self, connection, url_params = None, request_body = None, headers=None):
        status, data = connection.execute(self.put_verb.query, self.merge(url_params, request_body, headers), self.put_verb.commit)
        return self.respond(self.put_verb, status, data)
            
    def executePost(self, connection, url_params=None, request_body=None, headers=None):
        if isinstance(request_body, list):
            status, data = connection.executeMany(self.post_verb.query,  self.merge(url_params, request_body, headers), self.post_verb.commit)
        else:
            status, data = connection.execute(self.post_verb.query, self.merge(url_params, request_body, headers), self.post_verb.commit)
        return self.respond(self.post_verb, status, data)

    def executeDelete(self, connection, url_params=None, request_body=None, headers=None):
        status, data = connection.execute(self.delete_verb.query, self.merge(url_params, request_body, headers), self.delete_verb.commit)
        return self.respond(self.delete_verb, status, data)

    def __str__(self):
        return "{path: %(path)s}" % {"path": self._path}

    def createVariableList(self, column_names, column_types):
        return_str = '{<br/>'
        for name, type in zip(column_names, column_types):
            return_str += '&nbsp;"' + name + '": ' + FieldType.get_info(type[1]) + ",<br/>"
        return_str = return_str[:-6]
        return return_str + '<br/>}'

    def createParameterList(self, parameters):
        if len(parameters) == 0:
            return "None<br/><br/>"
        return_str = '<ul>\n'
        for param in parameters:
            return_str += '<li>' + param + '</li>\n'
        return return_str + '</ul>\n'

    def createHtmlDiv(self, connection):
        return_div = ""
        for get_verb in self.get_verbs.values():
            column_names, column_types = connection.getQueryColumnInfo(get_verb.query, get_verb.empty_parameters)
            return_div += "<h3>GET " + self._path  \
                + "</h3><div>\n<p><b>Description</b><br/>%(description)s<br/><br/><b>URL Parameters</b><br/>%(parameters)s<b>Response Body</b><br/>%(columns)s</p></div>\n" \
                % {"columns": self.createVariableList(column_names, column_types),
                    "parameters": self.createParameterList(get_verb.parameters),
                    "description": get_verb.description}
        for post_verb in self.post_verbs:
            return_div += "<h3>POST" + self._path + "</h3><div>\n<p>Gooble Gobble</p></div>\n"
        for delete_verb in self.delete_verbs:
            return_div += "<h3>DELETE" + self._path + "</h3><div>\n<p>Gooble Gobble</p></div>\n"
        for put_verb in self.put_verbs:
            return_div += "<h3>PUT" + self._path + "</h3><div>\n<p>Gooble Gobble</p></div>\n"
        return return_div

    def respond(self, verb, query_status, data=None):
        if verb.empty_response and not data:
            return self.createResponse(verb.empty_response["status"], verb.empty_response["statusCode"])
        if query_status:
            return self.createSuccessResponse(data)
        else:
            return self.createFailureResponse()

    def createResponse(self, status, status_code, data=None):
        response = jsonify({"status": status, "data": data})
        response.status_code = status_code
        response.headers['Cache-Control'] = 'no-cache, no-store, no-transform, max-age=0'
        return response

    def createFailureResponse(self):
        return self.createResponse("failure", 500)

    def createSuccessResponse(self, data):
        return self.createResponse("success", 200, data)

class HelpRestEndpoint(RestEndpoint):
    def __init__(self, www_dir, path, endpoint_divs):
        self._endpoint_divs = endpoint_divs
        self._path = path
        self._www_dir = www_dir;

    def createJavascriptTags(self, filename):
        javascript_path = os.path.join(self._www_dir, filename)
        logger.debug("Reading javascript file: " + javascript_path)
        f = open(javascript_path)
        contents = f.read()
        f.close()
        return '\n<script type="text/javascript">\n' + contents + '\n</script>\n'

    def createCssTags(self, filename):
        css_path = os.path.join(self._www_dir, filename)
        logger.debug("Reading css file: " + css_path)
        f = open(css_path)
        contents = f.read()
        f.close()
        return '\n<style>\n' + contents + '\n</style>\n'

    def executeGet(self, connection, url_params_str=None, request_body_str=None):
        help_path = os.path.join(self._www_dir, "help.html")
        logger.debug("Reading help file: " + help_path)
        f = open(help_path)
        html = f.read()
        f.close()
        return html % {"imports": self.createJavascriptTags('jquery/jquery-1.11.3.min.js')
            + self.createJavascriptTags('jquery/jquery-ui.min.js')
            + self.createCssTags('jquery/jquery-ui.min.css')
            + self.createCssTags('jquery/jquery-ui.theme.min.css'),
            "endpoints": self._endpoint_divs}

class RestHttpServer():

    def __init__(self, database_connection):
        self.endpoints = {}
        self._connection = database_connection
        self._connection.checkConnection()
        self._users = {}

    def addUser(self, username, password):
        if username and password:
            self._users[username] = User(username, password)

    def authenticate(self, username, password):
        return username and password and username in self._users and self._users[username].authenticate(username, password)

    def addEndpoint(self, endpoint):
        logger.info("Adding new endpoint: " + str(endpoint))
        self.endpoints[endpoint._path] = endpoint

    def getEndpoint(self, path):
        if path in self.endpoints:
            return self.endpoints[path]
        else:
            logger.warn('Unable to respond to request: ' + path)
            return None

    def shutdown(self):
        self._connection.close()

    def getConnection(self):
        return self._connection

    def createEndpointDivs(self):
        rtrn_str = ""
        for e in self.endpoints.values():
            #logging.info("Creating div for: " + str(type(endpoint)))
            rtrn_str += (e.createHtmlDiv(self._connection))
        return rtrn_str

    @staticmethod
    def createFromConfig():
        logger.info("Reading config file: " + default_config)
        f = open(default_config, "r")
        config_str = f.read()
        f.close()
        config = json.loads(config_str)
        db_ip = config["database_ip_address"]
        db = config["database"]
        db_user = config["database_user"]
        db_password = config["database_password"]
        database_pool_size = config["database_pool_size"]
        connection = MySqlConnection(db_ip, db, db_user, db_password, database_pool_size, "rest-datastore")
        httpd = RestHttpServer(connection)
        httpd.version = config["version"]

        for user in config["users"]:
            httpd.addUser(user["username"], user["password"])
        for endpoint in config["endpoints"]:
            path = endpoint["path"]
            new_endpoint = RestEndpoint(path)
            if "get" in endpoint:
                get = endpoint["get"]
                new_endpoint.setGet(RestVerb.createInstanceFromConfig(get))
            if "post" in endpoint:
                post = endpoint["post"]
                new_endpoint.setPost(RestVerb.createInstanceFromConfig(post))
            if "put" in endpoint:
                put = endpoint["put"]
                new_endpoint.setPut(RestVerb.createInstanceFromConfig(put))
            if "delete" in endpoint:
                delete = endpoint["delete"]
                new_endpoint.setDelete(RestVerb.createInstanceFromConfig(delete))
            httpd.addEndpoint(new_endpoint)
        for task in config["tasks"]:
            execfile(os.path.join(default_tasks_dir, task["file"]))
            pass
        return httpd

app = Flask(__name__)

server = RestHttpServer.createFromConfig()

def respondInvalidCredentials():
    return Response(
                    'Could not verify your account.\n'
                    'You have to login with proper credentials', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def respondInvalidPermissions():
    return Response(
                    'Could not verify your permissions for that URL.\n'
                    'You have to login with proper credentials', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def check_auth(username, password):
    return server.authenticate(username, password)

def requires_auth(f):
    @wraps(f)
    def decorated(*args, ** kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return respondInvalidCredentials()
        return f(*args, ** kwargs)
    return decorated

@app.route('/<endpoint>', methods=['POST'])
@requires_auth
def post(endpoint):
    logger.debug("Received a POST request.")
    endpoint = server.getEndpoint(endpoint)
    auth = request.authorization
    if endpoint and not endpoint.isValidUserPost(auth.username):
        return respondInvalidPermissions()
    connection = server.getConnection()
    if (endpoint):
        return endpoint.executePost(connection, request.args, request.get_json(), request.headers)
    else:
        abort(404)

@app.route('/<endpoint>', methods=['GET'])
@requires_auth
def get(endpoint):
    logger.debug("Received a GET request with args: " + str(request.args))
    endpoint = server.getEndpoint(endpoint)
    auth = request.authorization
    if endpoint and not endpoint.isValidUserGet(auth.username):
        return respondInvalidPermissions()
    connection = server.getConnection()
    if (endpoint):
        return endpoint.executeGet(connection, request.args.to_dict(flat=True), request.get_json(), request.headers)
    else:
        abort(404)

format_adapter = JsonAdapter()


@app.route('/<endpoint>', methods=['PUT'])
@requires_auth
def put(endpoint):
    logger.debug("Received a PUT request.")
    endpoint = server.getEndpoint(endpoint)
    auth = request.authorization
    if endpoint and not endpoint.isValidUserPut(auth.username):
        return respondInvalidPermissions()
    connection = server.getConnection()
    if (endpoint):
        return endpoint.executePut(connection, request.args,  request.get_json(), request.headers)
    else:
        abort(404)

@app.route('/<endpoint>', methods=['DELETE'])
@requires_auth
def delete(endpoint):
    logger.debug("Received a DELETE request.")
    endpoint = server.getEndpoint(endpoint)
    auth = request.authorization
    if endpoint and not endpoint.isValidUserDelete(auth.username):
        return respondInvalidPermissions()
    connection = server.getConnection()
    if (endpoint):
        return endpoint.executeDelete(connection, request.args, request.get_json(), request.headers)
    else:
        abort(404)

@app.route('/templates/<string:page_name>')
def static_page(page_name):
    return render_template(page_name)

@app.route('/heartbeat')
def heartbeat():
    return jsonify({"version": server.version})

#logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
#server.addEndpoint(HelpRestEndpoint(args.www[0], "/", httpd.createEndpointDivs()))
atexit.register(server.shutdown)

if __name__ == "__main__":
    app.run()
