# Internet of Things Rest Datastore

## Overview
This software is a Python Flask web server and database adapter that transforms Relational datastores to REST endpoints.  Currently, it supports MySQL.  It can be run through WSGI for a high-performance production service.  New IOT integrations are easy to add.  Security roles are included on each endpoint.

Here's how it works:
1) Create a database schema.
2) Create a JSON config file with SQL queries that map to endpoints.
3) Deploy your server.
4) Connect your IOT devices and start sending events.

## Installation
Setting up Debian:

     apt-get install python-pip mysql-server default-libmysqlclient-dev requests
 
 Installing Python dependencies:
 
     pip install flask mysql schedule mysql-connector

## Configuration File

### Authentication
Create passwords for each user in the config file.  Here is an example:

    # python
    >>> import hashlib
    >>> hashlib.sha224("admin password").hexdigest()
    'b025d883b5d875a10649fcdb6d89fd22aaf1589ae478988042722479'
    >>> hashlib.sha224("sensor password").hexdigest()
    '5d3e1fb726bfbbf59fc276aeb73dc36d2dc916031525213fd64effad'
    
Paste the hashed passwords back into the configuration file.

### Setup MySQL Database User and Password

  - database - The name of your MySQL database
  - database_user - The name of your MySQL user
  - database_password - The pasword for your MySQL user

## Example

### Create Example Database

Create an example database and account:

    # mysql
    > create database EXAMPLE;
    > CREATE USER 'example-user'@'localhost' IDENTIFIED BY 'password';
    > GRANT ALL PRIVILEGES ON EXAMPLE.* TO 'example-user'@'localhost';
    > exit

Create the example table:

    # $ mysql -u example-user -p < example/example.sql

Run the server (local testing mode):

    ./ird/ird.py --config example/example.json
    INFO:Reading config file: example/example.json
    INFO:Connecting to database: EXAMPLE
    INFO:Adding new endpoint: {path: sensor-event}
     * Serving Flask app "ird" (lazy loading)
     * Environment: production
       WARNING: Do not use the development server in a production environment.
       Use a production WSGI server instead.
     * Debug mode: off
    INFO: * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)

### Run the Example Unit Tests

With the server running, run the example unit tests:

    $ ./example/test-example.py 
    .Here is the example output from the GET endpoint:
    {u'status': u'success', u'data': [{u'RAW_VALUE': 0.77, u'ID': 1, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:19:34 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 2, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:20:40 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 3, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:21:22 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 4, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:23:11 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 5, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:23:40 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 6, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:24:17 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 7, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:24:32 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 8, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:24:47 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 9, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:25:13 GMT'}, {u'RAW_VALUE': 0.77, u'ID': 10, u'EVENT_TIMESTAMP': u'Sat, 22 Dec 2018 15:37:35 GMT'}]}
    .
    ----------------------------------------------------------------------
    Ran 2 tests in 0.021s
    
    OK


