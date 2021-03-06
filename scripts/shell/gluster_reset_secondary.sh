echo "Unmounting admin_vol"
umount /opt/integralstor/integralstor_gridcell/config

echo "Removing pools ..."
zfs destroy frzpool/normal/integralstor_admin_vol
rm -rf /frzpool/normal/integralstor_admin_vol

echo "Editing fstab"
sed -i '/localhost/d' /etc/fstab


echo "Stopping salt-minion"
service salt-minion stop

echo "Deleting salt pki"
rm -rf /etc/salt/pki

echo "Starting salt-minion"
service salt-minion restart

echo "Restarting glusterd"
service glusterd restart

