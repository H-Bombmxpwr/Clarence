import requests
from profanity_filter import ProfanityFilter

#from profanity_filter import ProfanityFilter
days = ["Thursday","thursday","thurday","4th day of the week"]


#getting the lyrics to be the bots status
song = "who hurt you daniel caesar"
pf = ProfanityFilter()
load = requests.get(f"https://some-random-api.ml/lyrics?title={song}").json()
lyrics = load['lyrics']
lyrics = pf.censor(lyrics)
status1 = lyrics.split("\n")


thedan = ["steely dan","Steely dan","the dan","donald and walter","don and walt","walt and don","walter and donald"]

emojis = ['😂','🙌','👍','😁','😎','😵‍💫','🦕','😈','💀','💩','🦄','🎅','🙅‍♀️','🙅‍♂️','🙅','🤦‍♂️','🤦‍♀️','🤦','😮','😥','🦌','🦬','🙎‍♂️','🙎','🙎‍♀️','👩‍🦼','👨‍🦯','🤾‍♂️','💅','🙌','👊','👎','👍','👌','👆','🤏','🧨','🎆','🎈','🎃']

snarky = ["shut up", "could not care less", "the world was better without this","callarse la boca","didn't ask","literally shut up", "yikes","keep thine trap shut", "put a sock in it","literally no one asked","seriously?","no me importa"]