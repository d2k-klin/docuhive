# Host-loss drill

Start a clean host with no running DocuHive services and no access to the old database.
Use only the operations/NAS/remote-access guides and a known backup snapshot.

Follow [full recovery](../scripts/restore.md), restoring private configuration from its
independent copy. Time from host availability to working sign-in, PDF preview, search,
resumed staged input and a new successful backup. The target is two hours.

Record missing steps and fix the runbooks. Keep the original deployment disconnected while
checking the recovery so mail jobs cannot run twice. Do not destroy the source host to test.
