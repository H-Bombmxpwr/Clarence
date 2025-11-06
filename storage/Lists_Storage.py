import requests
from better_profanity import profanity
#from profanity_filter import ProfanityFilter

#from profanity_filter import ProfanityFilter
days = ["Thursday","thursday","thurday","4th day of the week"]




thedan = ["steely dan","Steely dan","the dan","donald and walter","don and walt","walt and don","walter and donald"]

emojis = ['😂','🙌','👍','😁','😎','😵‍💫','🦕','😈','💀','💩','🦄','🎅','🙅‍♀️','🙅‍♂️','🙅','🤦‍♂️','🤦‍♀️','🤦','😮','😥','🦌','🦬','🙎‍♂️','🙎','🙎‍♀️','👩‍🦼','👨‍🦯','🤾‍♂️','💅','🙌','👊','👎','👍','👌','👆','🤏','🧨','🎆','🎈','🎃']

snarky = ["shut up", "could not care less", "the world was better without this","callarse la boca","didn't ask","literally shut up", "yikes","keep thine trap shut", "put a sock in it","literally no one asked","seriously?","no me importa"]

flag_emoji_dict = { # all of the suported flag emojis
"🇺🇸": "en",
"🇩🇪": "de",
"🇫🇷": "fr",
"🇪🇸": "es",
"🇮🇹": "it",
"🇵🇹": "pt",
"🇷🇺": "ru",
"🇦🇱": "sq",
"🇸🇦": "ar",
"🇧🇦": "bs",
"🇧🇬": "bg",
"🇨🇳": "zh-CN",
"🇭🇷": "hr",
"🇨🇿": "cs",
"🇩🇰": "da",
"🇪🇪": "et",
"🇫🇮": "fi",
"🇬🇷": "el",
"🇭🇺": "hu",
"🇮🇩": "id",
"🇮🇳": "hi",
"🇮🇪": "ga",
"🇮🇸": "is",
"🇮🇱": "he",
"🇯🇵": "ja",
"🇰🇷": "ko",
"🇱🇻": "lv",
"🇱🇹": "lt",
"🇲🇹": "mt",
"🇲🇪": "sr",
"🇳🇱": "nl",
"🇳🇴": "no",
"🇵🇰": "ur",
"🇵🇱": "pl",
"🇵🇹": "pt",
"🇷🇴": "ro",
"🇷🇸": "sr",
"🇸🇦": "ar",
"🇸🇰": "sk",
"🇸🇮": "sl",
"🇸🇬": "sv",
"🇹🇭": "th",
"🇹🇷": "tr",
"🇹🇼": "zh-TW",
"🇺🇦": "uk",
"🇻🇦": "la"
}

table = { #a list of all of the characters to ignore in profanity filter
    "\"": None,
    "'": None,
    "-": None,
    "`": None,
    "~": None,
    ",": None,
    ".": None,
    ":": None,
    ";": None,
    "*": None,
    " ": None,
    "_": None
}