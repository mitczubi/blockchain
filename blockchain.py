import hashlib
import json
import requests
from time import time
from uuid import uuid4
from textwrap import dedent
from flask import Flask, jsonify, request
from urllib.parse import urlparse

class Blockchain(object):
    def __init__(self):
        self.chain = [] #initialize two empty lists to store the Blockchain
        self.current_transactions = []
        self.nodes = set()

        #create the genesis Block
        self.new_block(previous_hash='1', proof=100)

    def register_node(self, address):
        """Add a new node to the list of nodes

            :param address: <str> address of a node
            :return: none"""

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def new_block(self, proof, previous_hash):
        """creates a new block in the Blockchain

            :param proof: <int> the proof is given by the proof of work algorithm
            :param previous_hash: the hash of the previous Block
            :return: <dict> New block"""

        block = {
            'index': len(self.chain) + 1,
            'time' : time(),
            'transactions' : self.current_transactions,
            'proof' : proof,
            'previous_hash' : previous_hash or self.hash(self.chain[-1])
            }

        self.current_transactions = [] #reset current_transactions
        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """creates a new transaction to go into the next mined block

            :param sender: <str> Address of sender
            :param recipient: <str> Address of recipient
            :param amount: <int> the index of the block that will hold this transaction
            :return: <int> the index of the Block that will hold this transaction"""

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount' : amount
            })

        return self.lastBlock['index'] + 1

    def validChain(self, chain):
        """Determine if a given blockchain is valid

            :param chain: <list> A Blockchain
            :return: <bool> If chain is valid or not"""

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print('{lastBlock}'.format(lastBlock=last_block))
            print('{block}'.format(block=block))
            print('\n----------------\n')
            #check the hash of the blockchain
            if block['previous_hash'] != self.hash(last_block):
                return False

            #check the PoW
            if not self.validProof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolveConflicts(self):
        """This is the consensus algorithm it replaces current chain with longest
            in the network

            :return: <bool> True if chain was replaced, False if not"""

        neighbors = self.nodes
        new_chain = None

        max_length = len(self.chain) #only looking for chains longer than thise

        for node in neighbors:
            response = requests.get('http://{node}/chain'.format(node=node))

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                if length > max_length and self.validChain(chain): #checks if chain length is longer
                    max_length = length
                    new_chain = chain

        if new_chain: #replace our exisiting chain if we found a longer better one
            self.chain = new_chain
            return True
        return False

    @staticmethod
    def hash(block):
        #Hash the block
        """ creates SHA-256 hash of a block

            :param block: <dict> Block
            :return: <str>"""

        #order the dict otherwise we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def lastBlock(self):
        #returns the last Blockchain
        return self.chain[-1]

    def proofOfWork(self, last_proof):
        """Simple proof of work algorithm:
            Find a number p' s.t. hash(pp') contains leading 4 zeroes, where p is
            the previous proof and p' is the new proof

            :param last_proof: <int>
            :return: <int>"""

        proof = 0
        while self.validProof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def validProof(last_proof, proof):
        """validates the proof: checks if hash(last_proof, proof) contains leading 4 zeroes

            :param last_proof: <int> previous proof
            :param proof: <int> current proof
            :return: <bool> True if correct, False if not"""

        guess = '{last_proof}{proof}'.format(last_proof=last_proof, proof=proof).encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

#instanstiate the node
app = Flask(__name__)

#generate a unique address for thise node
node_identifier = str(uuid4()).replace('-', '')

#instanstiate Blockchain
blockchain = Blockchain()

@app.route('/mine', methods=['GET'])
def mine():
    #run the PoW algorithm to get the next proof
    last_block = blockchain.lastBlock
    last_proof = last_block['proof']
    proof = blockchain.proofOfWork(last_proof)

    #Reward is received for our work
    #the sender is 0 to show this block has mined a new coin
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1
    )

    # make the new block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index' : block['index'],
        'transactions' : block['transactions'],
        'proof' : block['proof'],
        'previous_hash' : block['previous_hash']
    }
    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    #check if the required fields are in the data POST'ed
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    #create the transaction
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message' : 'Transaction will be added to Block {index}'.format(index=index)}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain' : blockchain.chain,
        'length' : len(blockchain.chain)
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')

    if nodes is None:
        return "Error: please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message' : 'New nodes have been added',
        'total_nodes' : list(blockchain.nodes)
    }

    return jsonify(response), 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolveConflicts()

    if replaced:
        response = {
            'message' : 'Our chain was replaced',
            'new_chain' : blockchain.chain
    }

    else:
        response = {
            'message' : 'Our chain is authoritative',
            'chain' : blockchain.chain
    }

    return jsonify(response), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
