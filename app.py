from cmath import e
from email import header
import json
from queue import Empty
from DateTimeEncoder import DateTimeEncoder
import pytz
from dateutil.parser import *
import os
from posixpath import split
import re
import threading
from traceback import print_tb
from http import client
from sqlite3 import connect
from unittest import result
from wsgiref import headers
from azure.data.tables import TableServiceClient
from azure.data.tables import UpdateMode
from urllib import response
from flask import Flask,jsonify, redirect,request,make_response,render_template,current_app
from flask_cors import CORS
import datetime
from microsoftgraph.client import Client

from Data import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, SCOPE, T_CONNECTION
template_dir = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
template_dir=os.path.join(template_dir, 'templates')
app = Flask(__name__)
CORS(app)
client=Client(CLIENT_ID,CLIENT_SECRET,account_type='common')
regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
def string_to_array(line):
    return line.split("/")
def get_table_client():
    t_client=TableServiceClient.from_connection_string(conn_str=T_CONNECTION)
    table_client = t_client.get_table_client(table_name="mailscraperapi")
    return table_client
    
def isValid(email):
    if re.fullmatch(regex, email):
      return True
    else:
        return False
def update_user(user):
    t_client=get_table_client()
    db_user=t_client.get_entity(partition_key=user["PartitionKey"],row_key=user["RowKey"])  
    db_user["access_token"]=user["access_token"]
    db_user["refresh_token"]=user["refresh_token"]
    db_user["refresh_token_date"]=datetime.datetime.now()
    t_client.update_entity(mode=UpdateMode.REPLACE,entity=db_user)
    return db_user
def update_user_subscription(user):
    t_client=get_table_client()
    db_user=t_client.get_entity(partition_key=user["PartitionKey"],row_key=user["RowKey"])  
    db_user["subscription_id"]=user["subscription_id"]
    db_user["subscription_expiry_date"]=user["subscription_expiry_date"]
    db_user["subscribed"]=user["subscribed"]
    t_client.update_entity(mode=UpdateMode.REPLACE,entity=db_user)
    return db_user
def renew_subscription(user):
 try:
    res=client.webhooks.renew_subscription(user["subscription_id"], datetime.datetime.now()+datetime.timedelta(days=2))
    if res.status_code==200:
        print(res.data)
        return res.data
    else:
        return {"status":400,"Message":"Something went wrong Please try again"}
 except Exception as e:   
    return print(str(e))
def get_user_acount():
    res_user=client.users.get_me()
    
    if res_user.status_code==200:
        user={
            "status":200,
            "user":res_user.data
        }
        return user
    else:
        user={
            "status":400,
            "Message":"Something went wrong Please try again"
        }
    return user
def refresh_token(user):
    response =client.refresh_token(REDIRECT_URI,user["refresh_token"])
    if response.status_code==200:
        tokens=response.data
        return tokens
    
def get_last_date(date):
    Last_date = {'date':date}
    Last_date=json.dumps(Last_date,cls=DateTimeEncoder)
    Last_date=json.loads(Last_date)
    Last_date=parse(Last_date["date"])
    return Last_date
def get_all_users():
    table_client=get_table_client()
    parameters = {
    "refresh_token_date":datetime.datetime.now()-datetime.timedelta(days=1)
}
    query_filter = ""
    entities=table_client.query_entities(query_filter,headers={'Content-Type':'application/json;odata=nometadata'})
    user={}
    users=[]
    t=0
    for entity in entities: 
        users.append(entity)
            #users=jsonify(users)
    return users
@app.route('/update_access_token',methods=['POST','GET'])
def update_access_token():
    users=get_all_users()
    def updates(**kwargs):
        users=kwargs.get("users",{})
        print(users)
        if not users:
            return "No Users",200
        else:
            for i,user in enumerate(users):
                tokens=refresh_token(user)
                user["refresh_token"]=tokens["refresh_token"]
                user["access_token"]=tokens["access_token"]
                set_current_user(tokens)
                update_user(user)
                sub=renew_subscription(user)
                user["subscription_id"]=sub["id"]
                user["subscription_expiry_date"]=sub["expirationDateTime"]
                update_user_subscription(user)
            return "Updated"
    thread = threading.Thread(target=updates,kwargs={'users': users})
    thread.start()
    return jsonify({"status":"Success"}),200   
def create_user_in_table(user_details,tokens):
    user={
        u'PartitionKey':user_details["user"]["id"],
        u'RowKey':user_details["user"]["userPrincipalName"],
        u'name':"N/A" if user_details["user"]["displayName"]==None else user_details["user"]["displayName"],
        u'email': "not available"  if user_details["user"]["mail"]==None else  user_details["user"]["mail"] ,
        u'access_token':tokens["access_token"],
        u'refresh_token':tokens["refresh_token"],
        u'refresh_token_date':datetime.datetime.now(),
        u'subscription_id':'1234567890',
        u'subscription_expiry_date':datetime.datetime.now(),
        u'subscribed':0,
        u'last_notification':'N/A',
        u'last_notification_date_time':datetime.datetime.now(),
        u'webhook':'N/A',
        u'signup_date':datetime.datetime.now(),
    }
    t_client=TableServiceClient.from_connection_string(conn_str=T_CONNECTION)
    table_client = t_client.get_table_client(table_name="mailscraperapi")
    user_cre=table_client.create_entity(entity=user)
    return user_cre
def subscribe_user(user):
    response=client.webhooks.create_subscription("created","https://aisafetymailscrapper.azurewebsites.net/webhook","/me/messages",datetime.datetime.now()+datetime.timedelta(days=2),None)
    #print(response.status_code)
    if(response.status_code==201):
        #print (response.data)
        user["subscription_id"]=response.data["id"]
        user["subscription_expiry_date"]=parse(response.data["expirationDateTime"])
        user["subscribed"]=1
        update_user_subscription(user)
    else:
        raise Exception("Something went wrong in Creating Subscription Please try again")
    return "yes"
def retrive_user(email_id):
    table_client=get_table_client()
    my_filter=''
    if(isValid(email_id)):
        my_filter = "RowKey eq '"+email_id+"'"
    else:
        my_filter = "PartitionKey eq '"+email_id+"'"
    entities = table_client.query_entities(my_filter)
    user={}
    t=0
    for entity in entities: 
        for key in entity.keys():
            t=t+1
            user[key]=entity[key]

    if t==0:
        user={
            "status":400,
            "user":"Not found"
        }
        return user
    else:
        user["status"]=200
        return user
def save_token(tokens,user):
    
    return True
def edit_user_table():
    return
def get_message(message_id):
    resp=client.mail.get_message(message_id)
    if(resp.status_code==200):
        #print(resp.data)
        return resp.data
    return "Not found"
def get_Token_from_code(code):
    redirect_url=REDIRECT_URI
    response = client.exchange_code(redirect_url,code)
    if response.status_code==200:
        a_t=str(response.data['access_token'])
        r_t=str(response.data['refresh_token'])
        tokens={
            "status":200,
            "access_token":a_t,
            "refresh_token":r_t
            ,
        }
        return tokens
    else:
        tokens={
            "status":400,
            "Message":"Something went wrong Please try again"
        }
        return tokens
def save_email(user,message):
    user={
        u'PartitionKey':message["id"],
        u'RowKey':user["RowKey"],
        u'From':message["from"]["emailAddress"]["address"],
        u'Sent_date_time':message["sentDateTime"],
        u'Subject':message["subject"],
        u'content':message["body"]["content"],
    }
    
    try:
        azure_func_url = "https://aisafety-outlook-inference-api.azurewebsites.net/api/Function-Outlook-Inference-API?code=nTTLBI/fg72QcBOQ8aDtoswJGDNnZJqJADxRqtFIH0XTYXZJ5NeDKQ=="
        azure_func_url += "&request_type=fromapp" + "&emailfrom=" + message["from"]["emailAddress"]["address"] + "&emailsubject=" + message["subject"] + "&hashstring=dd806"
        data = {"emailbody": message["body"]["content"]}
        data_json = json.dumps(data)
        response = requests.post(azure_func_url, json=data_json)
    except:
        pass
    
    t_client=TableServiceClient.from_connection_string(conn_str=T_CONNECTION)
    table_client = t_client.get_table_client(table_name="UserAction")
    user_cre=table_client.create_entity(entity=user)
    
def set_current_user(tokens):
    client.set_token(tokens)
    return True
def retrive_mails():
     resp=client.mail.list_messages()
     if resp.status_code==200:
         return resp.data
     return False
@app.route('/show_welcome')
def show_welcome():
    return "Welcome to the API"
@app.route('/webhook',methods=['GET','POST'])
def web_hook_callback():
    if request.args.get('validationToken') != None:
        return request.args.get('validationToken'),200
    data=request.get_json()
    def save_received_mail(**kwargs):
        data=kwargs.get("data",{})
        data=data["value"]
        res_data=string_to_array(data[0]['resourceData']['@odata.id']) 
        user=retrive_user(res_data[1])
        tokens=refresh_token(user)
        user["refresh_token"]=tokens["refresh_token"]
        user["access_token"]=tokens["access_token"]
        set_current_user(tokens)
        update_user(user)
        if(user["status"]==200):
            message=get_message(res_data[3])
            save_email(user,message)
    thread = threading.Thread(target=save_received_mail, kwargs={
                    'data': data})
    thread.start()
    #print("Mail_received")
    return "Mail Received",200
@app.route('/subscribe',methods=['GET','POST'])
def subscribe():
#  try:
    if request.form['email'] != None and request.form['email'] != '':
            mail_client=request.form['email']
            if isValid(mail_client):
                user=retrive_user(mail_client)
                if user["status"]==400:
                    url_gen=url_generator()
                    return redirect(url_gen)
            tokens=refresh_token(user)
            user["access_token"]=tokens["access_token"]
            user["refresh_token"]=tokens["refresh_token"]
            update_user(user)
            set_current_user(tokens)
            if(user["subscribed"]==0):
                #print('Triigered')
                subscribe_user(user)
            #data=retrive_mails()
            return "Subscribed",200 
#  except Exception as e:
#      return redirect('/')    
        
def url_generator():
     redirect_uri=REDIRECT_URI
     url = client.authorization_url(redirect_uri,SCOPE,None)
     return url
@app.route('/authcallback',methods=['GET', 'POST'])
def get_url():
     if request.args.get('code') is not None and request.args.get('code') != '':
        try:
                code = request.args.get('code')
                tokens=get_Token_from_code(code)
                if tokens['status']==200:
                    set_current_user(tokens)
                    user_details=get_user_acount()
                    user=retrive_user(user_details["user"]["userPrincipalName"])
                    if user["status"]==400:
                        user_cre=create_user_in_table(user_details,tokens)
                        user=retrive_user(user_details["user"]["userPrincipalName"])
                        subscribe_user(user)
                        #data=retrive_mails()
                    # save_token(tokens,user_details)
                        return "Subscribed Sucessfully",200
                    else:
                        user["access_token"]=tokens["access_token"]
                        user["refresh_token"]=tokens["refresh_token"]
                        update_user(user)
                        if(user["subscribed"]==0):
                            subscribe_user(user)
                            #data=retrive_mails()
                            return "Already Subscribed",200
                        return "Already Subscribed",200
                        # return redirect("/?msg=User already exists")
        except Exception as e:
                return "Status:Failed"+str(e)
     else:
        return redirect("/")
# @app.route("/loop",methods=['GET','POST'])
# def loop():
#   val=[{'subscriptionId': '9adbbc59-74af-4b59-befa-429249a42c6a', 'subscriptionExpirationDateTime': '2022-04-15T07:37:07.433529-07:00', 'changeType': 'created', 'resource': 'Users/410eacc136576223/Messages/AQMkADAwATMwMAItNGIwYi0xNjc5LTAwAi0wMAoARgAAA0V1Pwamy1tFpfjRi8Yb7MoHAPhDBm6LTulPreaPDKoBRIQAAAIBDAAAAPhDBm6LTulPreaPDKoBRIQAAAAIyrTnAAAA', 'resourceData': {'@odata.type': '#Microsoft.Graph.Message', '@odata.id': 'Users/410eacc136576223/Messages/AQMkADAwATMwMAItNGIwYi0xNjc5LTAwAi0wMAoARgAAA0V1Pwamy1tFpfjRi8Yb7MoHAPhDBm6LTulPreaPDKoBRIQAAAIBDAAAAPhDBm6LTulPreaPDKoBRIQAAAAIyrTnAAAA', '@odata.etag': 'W/"CQAAABYAAAD4QwZui07pT63mjwyqAUSEAAAIyO8f"', 'id': 'AQMkADAwATMwMAItNGIwYi0xNjc5LTAwAi0wMAoARgAAA0V1Pwamy1tFpfjRi8Yb7MoHAPhDBm6LTulPreaPDKoBRIQAAAIBDAAAAPhDBm6LTulPreaPDKoBRIQAAAAIyrTnAAAA'}, 'clientState': None, 'tenantId': ''}]
#   user_data=val[0]['resourceData']['@odata.id']
#   user_data=user_data.split("/")
#   #print(user_data)
#   return "Loop"
@app.route("/deletesubscription",methods=['GET','POST'])
def unsubscribe():
 try:    
    if(request.args["email"]):
        mail=request.args["email"]
        user=retrive_user(mail)
        if(user["status"]==200):
         if(user["subscribed"]==1):
            tokens=refresh_token(user)
            user["access_token"]=tokens["access_token"]
            user["refresh_token"]=tokens["refresh_token"]
            update_user(user)
            set_current_user(tokens)
            client.webhooks.delete_subscription(user["subscription_id"])
            user["subscription_id"]="Unsubscribed"
            user["subscribed"]=0
            user["subscription_expiry_date"]=''
            update_user_subscription(user)
            return "SuccessFuly Unsubscribed",200
        else:
            return "User is not subscribed",400
 except Exception as e:
      return str(e)
@app.route("/")
def hello_world():
    return render_template('index.html')
if __name__=="__main__":
    app.run(debug=True)     
