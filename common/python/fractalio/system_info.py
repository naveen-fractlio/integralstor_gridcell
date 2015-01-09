import os, re, socket, json, sys, types

import fractalio
from fractalio import common

import volume_info, gluster_commands


def load_system_config(first_time = False):

  if first_time:
    system_status_path = common.get_tmp_path()
  else:
    system_status_path = common.get_system_status_path()

  msfn = "%s/master.status"%system_status_path
  mmfn = "%s/master.manifest"%system_status_path

  with open(msfn, "r") as f:
    ms_nodes = json.load(f)
  with open(mmfn, "r") as f:
    mm_nodes = json.load(f)
  
  d = {}
  # First load it with the master node keys
  for k in mm_nodes.keys():
    d[k] = mm_nodes[k]
  '''
  for k in ms_nodes.keys():
    if k in mm_nodes:
      d[k] = mm_nodes[k]
  '''

  for k in d.keys():
    if k not in ms_nodes:
      continue
    status_node = ms_nodes[k]
    for sk in status_node.keys():
      if sk not in d[k]:
        d[k][sk] = status_node[sk]
      elif sk == "disks":
        for disk in status_node["disks"]:
          if disk in d[k]["disks"]:
            d[k]["disks"][disk].update(status_node["disks"][disk])
          else:
            d[k]["disks"][disk] = status_node["disks"][disk]
      elif sk == "interfaces":
        for interface in status_node["interfaces"]:
          if interface in d[k]["interfaces"]:
            d[k]["interfaces"][interface].update(status_node["interfaces"][interface])
          else:
            d[k]["interfaces"][interface] = status_node["interfaces"][interface]
    '''
    if k in d:
      #only update for those nodes that are in the manifest
      for k1 in ms_nodes[k].keys():
        if k1 in d[k] and type(d[k][k1]) is types.DictType:
          
          print d[k][k1]
          print ms_nodes[k][k1]
          d[k][k1].update(ms_nodes[k][k1])
        else:
          d[k][k1] = ms_nodes[k][k1]
    '''

  peer_list = gluster_commands.get_peer_list()
  #Need to add the localhost because it is never returned as part of the peer list
  localhost = socket.gethostname().strip()
  tmpd = {}
  tmpd["hostname"] = localhost
  tmpd["status"] = 1
  peer_list.append(tmpd)

  #assert False
  for k in d.keys():
    d[k]["in_cluster"] = False
    if peer_list:
      for peer in peer_list:
        if k == peer["hostname"]:
          d[k]["in_cluster"] = True
          d[k]["cluster_status"] = int(peer["status"])
      #if k in peer_list:
      #  d[k]["in_cluster"] = True
    d[k]["volume_list"] = volume_info.get_volumes_on_node(k, None)
  '''
  for k in d.keys():
    d[k]["in_cluster"] = False
    if peer_list:
      for peer in peer_list:
        if k == peer["hostname"]:
          d[k]["in_cluster"] = True
          d[k]["cluster_status"] = int(peer["status"])
      #if k in peer_list:
      #  d[k]["in_cluster"] = True
    d[k]["volume_list"] = integral_view.utils.volume_info.get_volumes_on_node(k, None)
  '''
  return d


def raid_enabled():
  #Enabled by default now. We need to change this to read from the config db which in turn will be updated at the time of first config
  return True



def get_available_node_list(si):
  #Return a list of nodes that can be pulled into the trusted pool. 
  nl = []
  for hostname, node in si.iteritems():
    if node["node_status"] != 0:
      continue
    if node["in_cluster"]:
      continue
    d = {}
    d["hostname"] = hostname
    d["host_info"] = node
    nl.append(d)
  return nl




def main():

  #print get_chassis_components_status()
  #print load_system_config()["host1"]
  #sl = load_system_config()
  #print "System config :"
  #print sl
  pass


if __name__ == "__main__":
  main()

'''
def get_addable_node_list(nl, spare_sled):
  # Returns the list of nodes that excludes the spare sled for purposes of form population
  anl = []
  #localhost = socket.gethostname().strip()
  for node in nl :
    #if node["sled"] == spare_sled or node["hostname"] == localhost:
    if node["sled"] == spare_sled :
      continue
    else:
      anl.append(node)
  return anl

def prompt_for_spare(nl):

  sl = []
  for node in nl:
    if node["sled"] not in sl:
      sl.append(node["sled"])
  if len(sl) == 1:
    return True
  else:
    return False
def generate_display_node_list(scl):

  if not scl:
    return None
  x = 0
  num_sled_rows = 3
  num_sleds_per_row = 4
  display_node_list = []
  for i in xrange(num_sled_rows):
    al = []
    for j in xrange(num_sleds_per_row):
      bl = []
      for k in xrange(2):
        bl.append(scl[x])
        x = x + 1
      al.append(bl)
    display_node_list.append(al)
  return display_node_list

def get_spare_sled(scl, nl):
  # Returns the spare sled number from the available node list
  sl = []
  for node in nl:
    if node["sled"] not in sl:
      sl.append(node["sled"])
  sl = sorted(sl)
  i = len(sl) -1
  spare_sled = -1
  #Starting from the last sled, make sure thatboth the nodes are not in the cluster just to cover for partially added sleds
  while i >= 0:
    print "node 1" 
    print scl[(sl[i]-1)*2]
    print "node 2" 
    print scl[(sl[i]-1)*2 + 1]
    if not scl[(sl[i]-1)*2]["in_cluster"] and not scl[(sl[i]-1)*2 + 1]["in_cluster"] and scl[(sl[i]-1)*2]["up"] and scl[(sl[i]-1)*2 + 1]["up"] and scl[(sl[i]-1)*2]["active"] and scl[(sl[i]-1)*2 + 1]["active"]:
      spare_sled = sl[i] 
      break
    else:
      i = i-1
  return spare_sled

def get_chassis_components_status():

  d = {}

  if production:
    sd = os.popen("ipmitool sdr")
    str4 = sd.read()
    lines = re.split("\r?\n", str4)
  else:
    with open("./ipmitool_output", "r") as f:
      lines = f.readlines()
  ipmi_status = []
  for line in lines:
    l = line.rstrip()
    print l
    comp_list = l.split('|')
    comp = comp_list[0].strip()
    status = comp_list[2].strip()
    if comp in["CPU Temp", "System Temp", "DIMMA1 Temp", "DIMMA2 Temp", "DIMMA3 Temp", "FAN1", "FAN2", "FAN3"] and status != "ns":
      td = {}
      td["reading"] = comp_list[1].strip()
      td["status"] = comp_list[2].strip()
      if comp == "CPU Temp":
        td["name"] = "CPU Temperature"
      elif "comp" == "System Temp":
        td["name"] = "System Temperature"
      elif "comp" == "DIMMA1 Temp":
        td["name"] = "Memory card 1 temperature"
      elif "comp" == "DIMMA2 Temp":
        td["name"] = "Memory card 2 temperature"
      elif "comp" == "DIMMA3 Temp":
        td["name"] = "Memory card 3 temperature"
      elif "comp" == "FAN1":
        td["name"] = "Fan 1 speed"
      elif "comp" == "FAN2":
        td["name"] = "Fan 2 speed"
      elif "comp" == "FAN3":
        td["name"] = "Fan 3 speed"
      ipmi_status.append(td)
  d["ipmi_status"] = ipmi_status
  print d

	
    reobj1 = re.compile("(Temp_Ambient\s)")
    list_T = []	
    for line in lines[:]:
      mini_T = {}
      if reobj1.search(line):
        #print line
        ent1 = re.search(r'\d+\s[a-zA-Z]+\s[C]', line)
        ent2 = re.search(r'\|\s[a-zA-Z]+', line)
        #print ent1.group()
        ent2_1= (ent2.group()).lstrip('|')
        #print ent2_1.strip()
        mini_T["status"] = ent2_1.strip()
        mini_T["temp"] = ent1.group()
        list_T.append(mini_T)
    dict1["temperature"] = list_T
    #print dict1["temperature"]

    list_F = []	
    reobj2 = re.compile("(Fan_.*)+")
    for line2 in lines[:]:	
    	mini_F = {}
    	if reobj2.search(line2):
    		#print line2
    		ent3 = re.search(r'Fan_[A-Z0-9]+_\d', line2)
    		ent4 = re.search(r'\s\d+\s[A-Z]+',line2)
    		ent5 = re.search(r'\|\s[a-zA-Z]+', line2)
    		#print ent3.group()
    		#print ent4.group()
    		ent5_1 = (ent5.group()).lstrip('|')
    		#print ent5_1.strip()
    		mini_F["name"] = ent3.group()
    		mini_F["RPM"] = ent4.group()
    		mini_F["status"] = ent5_1.strip()
    		#print mini_F
                list_F.append(mini_F)
  		
    #print list_F
    #list_F.append(mini_F)
    dict1["fans"]= list_F
    #print dict1
  
    list_P = []
    reobj3 = re.compile("(PSU\d_.*)+")
    for line3 in lines[:]:
    	mini_P = {}
    	if reobj3.search(line3):
    		#print line3
    		ent6 = re.search(r'PSU[0-9]_[a-zA-Z]+', line3)
    		ent7 = re.search(r'\s[0-9a-z]+', line3)
    		ent8 = re.search(r'\|\s[a-zA-Z]+', line3)
    		ent8_1 = (ent8.group()).lstrip('|')
  		
    		#print ent6.group()
    		#print (ent7.group()).strip()
    		#print ent8_1.strip()
  
    		mini_P["name"] = ent6.group()
    		mini_P["code"] = (ent7.group()).strip()
    		mini_P["status"] = ent8_1.strip()
    		list_P.append(mini_P)
  
    dict1["psus"] = list_P
  else:
    #dict1 = {'fans': [{'status': 'ok', 'RPM': ' 1560 RPM', 'name': 'Fan_SYS0_1'}, {'status': 'ok', 'RPM': ' 1680 RPM', 'name': 'Fan_SYS1_1'}, {'status': 'ok', 'RPM': ' 1740 RPM', 'name': 'Fan_SYS2_1'}, {'status': 'ok', 'RPM': ' 1680 RPM', 'name': 'Fan_SYS0_2'}, {'status': 'ok', 'RPM': ' 1680 RPM', 'name': 'Fan_SYS1_2'}, {'status': 'ok', 'RPM': ' 1620 RPM', 'name': 'Fan_SYS2_2'}, {'status': 'ok', 'RPM': ' 4380 RPM', 'name': 'Fan_SYS3_1'}, {'status': 'ok', 'RPM': ' 4320 RPM', 'name': 'Fan_SYS3_2'}], 'psus': [{'status': 'ok', 'code': '0x01', 'name': 'PSU1_Status'}, {'status': 'ok', 'code': '0x01', 'name': 'PSU2_Status'}], 'temperature': [{'status': 'ok', 'temp': '21 degrees C'}]}

    l = [{"hostname":"host1", "status":"healthy"}, {"hostname":"host2", "status":"degraded"}, {"hostname":"host3", "status":"down"}]
  return l
'''