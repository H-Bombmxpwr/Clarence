import requests
import os
import discord
from functionality.structures import Trivia
from replit import db
import json
import random
import html
from datetime import date
from requests import Session
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects



def check_carrot(string,message):
  for i in range(0,len(string)):
    if string[i] != '^':
      return 0
  
  if message.author.bot == True:
    return 0
  return 1


def get_insult():
  response = requests.get("https://evilinsult.com/generate_insult.php?lang=en&type=json")
  json_request = response.json()
  quote = html.unescape(json_request["insult"])
  return quote

def get_compliment():
  response = requests.get("https://8768zwfurd.execute-api.us-east-1.amazonaws.com/v1/compliments")
  json_request = response.json()
  quote = html.unescape(json_request)
  return quote



def get_joke():
  jokeurl = "https://v2.jokeapi.dev/joke/Any?type=twopart"

  response = requests.get(jokeurl)
  quote = response.json()
  return quote



def get_question2():
  headers = {'Content-Type': 'application/json'}
  response = requests.get("https://opentdb.com/api.php?amount=1&type=multiple", headers)
  json_request = response.json()
  
  #unescaping all all of the responses
  category = html.unescape(json_request["results"][0]["category"])
  question = html.unescape(json_request["results"][0]["question"])
  cor_ans = html.unescape(json_request["results"][0]["correct_answer"])
  in_ans1 = html.unescape(json_request["results"][0]["incorrect_answers"][0])
  in_ans2 = html.unescape(json_request["results"][0]["incorrect_answers"][1])
  in_ans3 = html.unescape(json_request["results"][0]["incorrect_answers"][2])

  in_ans = [in_ans1, in_ans2, in_ans3]
  
  #creating a trivia object and returning it
  trivia = Trivia(question, category, cor_ans, in_ans)

  return trivia




def coin_market_cap():

  url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
  parameters = {
  'start':'1',
  'limit':'5000',
  'convert':'USD'
}
  headers = {
  'Accepts': 'application/json',
  'X-CMC_PRO_API_KEY': os.getenv('coin_key'),
}

  session = Session()
  session.headers.update(headers)

  try:
    response = session.get(url, params=parameters)
    data = json.loads(response.text)
    print(data)
  except (ConnectionError, Timeout, TooManyRedirects) as e:
    print(e)





def update_score(ctx,temp):
  
  #adds user ID to the database
  if 'trivia' in db.keys():
  
    listin = db['trivia']
    if (ctx.author.name + '#' + ctx.author.discriminator) not in listin:
      listin.append(ctx.author.name + '#' + ctx.author.discriminator)
      listin.append(temp)
      listin.append(1)
    else:
      spot = listin.index(ctx.author.name + '#' + ctx.author.discriminator)
      listin[spot + 1] = listin[spot + 1] + temp
      listin[spot + 2] = listin[spot + 2] + 1
    db['trivia'] = listin
    
  else:
    listin = [ctx.author.name + '#' + ctx.author.discriminator,temp,1]
    db['trivia'] = listin



def get_trivia_stats(ctx):
  listin = db['trivia']
  stats = []

  if (ctx.author.name + '#' + ctx.author.discriminator) in listin:
    spot = listin.index(ctx.author.name + '#' + ctx.author.discriminator)
    stats.append(1)
    stats.append(listin[spot + 1])
    stats.append(listin[spot + 2])
  
  else:
    stats.append(0)
  
  return stats



def get_stats(ctx):
  listin = db['trivia']
  embedVar = discord.Embed(title = "Database of Trivia players",description = 'Currently tracking ' + str(round(len(listin)/3)) + ' players', color = 0x6a0dad).set_footer(text = "All scores as of " + str(date.today()))
  for x in range(0,len(listin) - 1,3):
    embedVar.add_field(name = listin[x], value = 'Correct: ' + str(listin[x+1]) + '\nTotal: ' + str(listin[x+2]) + '\nPercent: ' + str(round(listin[x+1]/listin[x+2] * 100 ,2)) + '%', inline = True)
  return embedVar



def update_fizzbuzz(ctx,count):
  
  #adds user ID to the database
  if 'fizzbuzz' in db.keys():
  
    listin = db['fizzbuzz']
    if (ctx.author.name + '#' + ctx.author.discriminator) not in listin:
      listin.append(ctx.author.name + '#' + ctx.author.discriminator)
      listin.append(count)
    else:
      spot = listin.index(ctx.author.name + '#' + ctx.author.discriminator)
      if listin[spot + 1] <  count:
        listin[spot + 1] = count
    db['fizzbuzz'] = listin
    
  else:
    listin = [ctx.author.name + '#' + ctx.author.discriminator,count]
    db['fizzbuzz'] = listin

    
def get_fizzbuzz_stats(ctx):
  listin = db['fizzbuzz']
  stats = []

  if (ctx.author.name + '#' + ctx.author.discriminator) in listin:
    spot = listin.index(ctx.author.name + '#' + ctx.author.discriminator)
    stats.append(listin[spot + 1])
  
  else:
    stats.append(0)
  
  return stats
  

def punish_user(user_id,word):
    user_id = '<@' + str(user_id) + '>'
    censor = word[0]

    for l in range(1,len(word)):
      censor =  censor + '\*'
    
    responses = [
      f"{user_id}, I think you meant to say {censor}",
      f"{censor} you too, {user_id}",
      f"Woah that should be {censor} in this Christian server,{user_id}",
      f"{user_id}...{user_id}...{user_id} cmon now, the least you could do is {censor}",
      f"{user_id}, leave something to the imagination, like {censor}",
      f"At least I have the dignity to say {censor}, {user_id}",
      f" You can come up with something more creative than {censor}, {user_id}",
      f"{censor} is what your mom said last night, {user_id}",
      f"{user_id}, let me write {censor} down so I can take this energy to yo MOMS house"]

      
    
    choice = random.choice(responses)

    return choice

  