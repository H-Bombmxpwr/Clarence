import random

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
    

class TrieNode:
    _MAX_SIZE = 40

    def __init__(self):
        self.children = [None] * self._MAX_SIZE
        self.is_end_of_word = False