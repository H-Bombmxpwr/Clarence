import time
def check_day(text):
      time_zone = -6
      mod_time = int((int(time.time()) + (time_zone * 3600)) / 86400) % 7
      #flat fuck friday
      if any(word in text for word in ["flat fuck friday","fuck flat friday"]):
          if  mod_time == 1:
              emoji = "🐊"
              
          else:
              emoji  = "❌"
          return emoji
      
      #milkie monday
      if any(word in text for word in ["milkie monday", "milkiemonday","milky monday","milkymonday"]):
        
  
        if mod_time == 4:
          emoji = "🥛"
        else:
          emoji = "❌"
        return emoji
        
      #no clothes tuesday
      if any(word in text for word in ["no clothes tuesday","noclothestuesday"]):
        if mod_time == 5:
          emoji = "🧦"
        else:
          emoji = "❌"
        return emoji

      # wet Wednesday 
      if any(word in text for word in ["wet wednesday","wetwednesday","wet wedsnday"]):
        if mod_time == 6:
          emoji = "🌊"
        else:
          emoji = "❌"
        return emoji

      return None