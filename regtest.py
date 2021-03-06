import sys
import os, time
data_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(data_dir, 'lib'))
import subprocess
import unittest
import common
from blockchaininterface import *
import bitcoin as btc
import binascii

'''Expectations
1. Any bot should run indefinitely irrespective of the input
messages it receives, except bots which perform a finite action

2. A bot must never spend an unacceptably high transaction fee.

3. A bot must explicitly reject interactions with another bot not
respecting the JoinMarket protocol for its version.

4. Bots must never send bitcoin data in the clear over the wire.
'''

'''helper functions put here to avoid polluting the main codebase.'''

import platform
OS = platform.system()
PINL = '\r\n' if OS == 'Windows' else '\n'

def local_command(command, bg=False, redirect=''):
    if redirect=='NULL':
	if OS=='Windows':
	    command.append(' > NUL 2>&1')
	elif OS=='Linux':
	    command.extend(['>', '/dev/null', '2>&1'])
	else:
	    print "OS not recognised, quitting."
    elif redirect:
	command.extend(['>', redirect])

    if bg:
	return subprocess.Popen(command, stdout=subprocess.PIPE,
	                        stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    else:
	#in case of foreground execution, we can use the output; if not
	#it doesn't matter
	return subprocess.check_output(command)
    

	
class Join2PTests(unittest.TestCase):
    def setUp(self):
        #create 2 new random wallets.
        #put 100 coins into the first receive address
        #to allow that bot to start.
        seed1, seed2 = [binascii.hexlify(x) for x in [os.urandom(15), os.urandom(15)]]
        self.wallets = {}
        wallet1 =  common.Wallet(seed1)
        wallet2 = common.Wallet(seed2)
        self.wallets[1] = {'seed':seed1,'wallet':wallet1}
        self.wallets[2] = {'seed':seed2,'wallet':wallet2}
        #get first address in each wallet
        addr1 = wallet1.get_receive_addr(0)
	common.debug("address for wallet1: "+addr1)
        addr2 = wallet2.get_receive_addr(0)
	common.debug("address for wallet2: "+addr2)
        common.bc_interface.grab_coins(addr1,10)
        common.bc_interface.grab_coins(addr2,10)
        
    def run_simple_send(self, n):
        #start yield generator with wallet1
	yigen_proc = local_command(['python','yield-generator.py', 
	                            str(self.wallets[1]['seed'])],redirect=self.wallets[1]['seed'],bg=True)
	
	#A significant delay is needed to wait for the yield generator to sync its wallet
	time.sleep(30)
	
	#run a single sendpayment call with wallet2
	amt = 100000000 #in satoshis
	dest_address = btc.privkey_to_address(os.urandom(32), common.get_addr_vbyte())
	try:
	    for i in range(n):
		sp_proc = local_command(['python','sendpayment.py','--yes','-N','1', self.wallets[2]['seed'],\
	                                       str(amt), dest_address])
	except subprocess.CalledProcessError, e:
	    if yigen_proc:
		yigen_proc.terminate()
	    print e.returncode
	    print e.message
	    raise

	if yigen_proc:
	    yigen_proc.terminate()
	
	#for cf in [self.wallets[1]['seed']+'_yieldgen.out', self.wallets[2]['seed']+'_send.out']:
	#    if os.path.isfile(cf):
	#	with open(cf, 'rb') as f:
	#	    if 'CRASHING' in f.read(): return False
	    
	received = common.bc_interface.get_received_by_addr([dest_address], None)['data'][0]['balance']
	if received != amt*n:
	    common.debug('received was: '+str(received)+ ' but amount was: '+str(amt))
	    return False
	return True
    	
    def test_simple_send(self):
        self.failUnless(self.run_simple_send(2))
	

class JoinNPTests(unittest.TestCase):
	
    def setUp(self):
	self.n = 2
        #create n+1 new random wallets.
        #put 10 coins into the first receive address
        #to allow that bot to start.
	seeds = map(None, *([iter(os.urandom((self.n+1)*15))]*15))
	
        seeds = [binascii.hexlify(''.join(x)) for x in seeds]
        self.wallets = {}
	for i, seed in enumerate(seeds):
	    self.wallets[i] = {'seed':seed, 'wallet':common.Wallet(seed)}

        #get first address in each wallet
	for i in self.wallets.keys():
	    common.bc_interface.grab_coins(self.wallets[i]['wallet'].get_receive_addr(0), amt=10)
	    
	#the sender is wallet (n+1), i.e. index wallets[n]
    
	
    def test_n_partySend(self):
	self.failUnless(self.run_nparty_join())
	
    def run_nparty_join(self):
	yigen_procs = []
	for i in range(self.n):
	    ygp = local_command(['python','yield-generator.py',\
	                         str(self.wallets[i]['seed'])], bg=True)
	    time.sleep(2) #give it a chance
	    yigen_procs.append(ygp)
	
	#A significant delay is needed to wait for the yield generators to sync 
	time.sleep(60)
	
	#run a single sendpayment call 
	amt = 100000000 #in satoshis
	dest_address = btc.privkey_to_address(os.urandom(32), common.get_addr_vbyte())	
	try:
	    sp_proc = local_command(['python','sendpayment.py','--yes','-N', str(self.n),\
	                             self.wallets[self.n]['seed'], str(amt), dest_address])
	except subprocess.CalledProcessError, e:
	    for ygp in yigen_procs:
		ygp.kill()
	    print e.returncode
	    print e.message
	    raise
	
	if any(yigen_procs):
	    for ygp in yigen_procs:
		ygp.kill()
	
	crash_files = [self.wallets[i]['seed']+'_yieldgen.out' for i in range(self.n)]
	crash_files.append(self.wallets[self.n]['seed']+'_send.out')
	for cf in crash_files:
	    if os.path.isfile(cf): return False
		#with open(cf, 'rb') as f:
		#    if 'CRASHING' in f.read(): return False
		    
	received = common.bc_interface.get_received_by_addr([dest_address], None)['data'][0]['balance']
	if received != amt:
	    return False
	return True	


def main():
    common.load_program_config()
    if not common.bc_interface:
	print 'not there'
	exit()
    unittest.main()

if __name__ == '__main__':
    main()
    

