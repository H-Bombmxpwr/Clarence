import discord




#The embeds for the about page of the bot
def make_list():

  color = 0x280137
  name = "Clarence Commands"
  embedVar1 = discord.Embed(title=name, description="Use `fulllist` to get one page of all the commands\n `help <command>` will break down the commands further", color=color)
  

  embedVar1.add_field(name= "Commands", value = '`Page 2: ` API Commands\n`Page 3: ` Local Commands\n`Page 4: ` Music Commands\n`Page 5: ` Moderation Commands\n`Page 6: ` Fun Commands',inline = False)
  
  embedVar2 = discord.Embed(title=name, description="[Invite](https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot)", color=color)
  embedVar2.add_field(name = "API Commands", value = "`          gif: ` + a query to pul the top GIF from tenor\n`         joke: ` Generate a (sometimes nsfw) joke\n  `         xkcd: ` to pull the latest/random xkcd comic\n `         meme: ` to generate a random meme\n `        query: ` Answer virtually any question\n`       trivia: ` to play trivia\n `       animal: ` + an animal to pull a picture of a given animal\n`       pickup: ` Generate a random pickup line\n`       insult: ` Generate insults\n`      twitter: ` to interact with twitter\n`      lichess: ` Grab the lichess daily puzzle\n`    wikipedia: ` + a query to get a wikipedia link\n`   compliment: ` Generate compliments \n")

  embedVar3 = discord.Embed(title=name, description="[Invite](https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot)", color=color)

  embedVar3.add_field(name = "Local Commands", value = " `     bug: ` to spam a user x number of times\n`    bits: ` convert decimal/hex/binary/ascii\n `    help: ` will return more info for every command\n`    list: ` List the bot commands\n`    ping: ` Get the latency of the bot\n`   ascii: ` + a < 16 string will print a ascii string of the text\n`  invite: ` Invite the bot\n`userinfo: ` return info of a server member\n")

  
  embedVar4 = discord.Embed(title=name, description="[Invite](https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot)", color=color)
  
  embedVar4.add_field(name = "Music Commands", value = "` music: ` to bring up a list of commands for the music player\n`lyrics: ` pull the lyrics to a requested song")

  embedVar5 = discord.Embed(title=name, description="[Invite](https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot)", color=color)

  embedVar5.add_field(name = "Moderation Commands" , value =  "`help Moderation: ` for a list of moderation commands\n•Moderation commands require special permissions to use")

  embedVar6 = discord.Embed(title=name, description="[Invite](https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot)", color=color)

  embedVar6.add_field(name = "Fun" , value =  '`    bored:` give you something to do while bored\n `   count: ` play a counting game\n`   ratio: ` ratio a worthy foe\n` collatz: ` run the collatz conjecture\n`fizzbuzz: ` play fizzbuzz\n`paradigm: ` random quote from 2070 paradigm shift\n`fiftytwo: ` play 52 card pickup', inline = False)

  embeds = [embedVar1,embedVar2,embedVar3,embedVar4,embedVar5,embedVar6]

  return embeds
  