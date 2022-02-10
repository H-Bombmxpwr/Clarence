import random

#class to support trivia command
class Trivia:
  def __init__(self, question, category, correctAnswer, incorrectAnswers):
    self.question = question
    self.category = category
    self.correctAnswer = correctAnswer
    self.incorrectAnswers = incorrectAnswers
  
  def print(self):
    print("Category: " + self.category)
    print("Question: " + self.question)
    print("Correct Answer: " + self.correctAnswer)
    for x in self.incorrectAnswers:
      print("Incorrect Answer: " + x)
  
  def getAnswerList(self):
    answers = []
    answers.append(self.correctAnswer)
    for x in self.incorrectAnswers:
      answers.append(x)
    random.shuffle(answers)
    return answers


#class to support the  fizzbuzz command
class FizzBuzz:
  def __init__(self, number):
    self.number = number

  def solve(self,number):
  
    if self.number % 15 == 0:
      value = "FizzBuzz"
    elif self.number % 3 == 0:
      value = "Fizz"
    elif self.number % 5 == 0:
      value = "Buzz"
    else:
      value = str(self.number)
    return value


#class to support the profanity filter trie
class TrieNode:
    _MAX_SIZE = 40

    def __init__(self):
        self.children = [None] * self._MAX_SIZE
        self.is_end_of_word = False

#class to support the fiftytwo command
class Card:
    def __init__(self, value, color):
        self.value = value
        self.color = color



#class to support the bits command
class Bits:
  
  def __init__(self,typ,value):
    self.value = value
    self.type = typ

  def to_decimal(self,typ,value):
    try:
      if typ == "d":
        value = int(value)
      elif typ == "h":
        value = int(value,16)
      elif typ == "a":
        value = ord(value)
      elif typ == "b":
        value = int(value,2)
      else:
        value = None
      return value
    except:
      return None

  def from_decimal(self,decimal):
    decimal = int(decimal)
    try:
      ascii = chr(decimal)
    except:
      ascii = "N/A"
    hexa = hex(decimal).replace("0x","").upper()
    binary = bin(decimal).replace("0b","")
    return decimal,ascii,hexa,binary
    




  

  
    




