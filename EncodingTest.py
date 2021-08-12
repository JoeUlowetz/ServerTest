# EncodingTest.py
import json
import ast

print("hello")

my_dict = {1: 'a', 2: 'b', 'abc': 123}
print(my_dict)
print("my_dict type:",type(my_dict))

print(" ")
my_json = json.dumps(my_dict)
print(my_json)
print("my_json type:", type(my_json))
# {"1": "a", "2": "b", "abc": 123}
#  1234567890
print( my_json[1:8])

print(" ")
#my_ast = ast.literal_eval(my_json)
#print(my_ast)
#print("my_ast type:", type(my_ast))

my_result = json.loads(my_json)
print(my_result)
print("my_result type:", type(my_result))
