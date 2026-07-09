from ceph.ceph_admin.orch import Orch
from cli.cephadm.cephadm import CephAdm
from cli.ceph.ceph import Ceph
from cli.utilities.operations import wait_for_cluster_health
from utility.log import Log

log = Log(__name__)


class StaggeredUpgradeError(Exception):
    pass


def run(ceph_cluster, **kw):
    """Staggered upgrade
    Args:
        **kw: Key/value pairs of configuration information to be used in the test
        kw: test data
        e.g:
        test:
            name: Staggered upgrade with daemon types mgr,mon
            desc: Staggered upgrade with daemon types mgr,mon
            module: test_cephadm_staggered_upgrade.py
            polarion-id: CEPH-83575554
            config:
                action: "daemon_types"
                osd_flags:
                - noout
                - noscrub
                - nodeep-scrub
                daemon_types: mgr,mon
    """
    config = kw.get("config")
    osd_flags = config.get("osd_flags")
    target_image = config.get("container_image")
    action = config.get("action")
    node = ceph_cluster.get_nodes(role="mon")[0]
    orch = Orch(cluster=ceph_cluster, **config)
    client = ceph_cluster.get_nodes(role="client")
    # Check cluster health before upgrade
    health = wait_for_cluster_health(client, "HEALTH_OK", 300, 10)
    if not health:
        # Get detailed health information to understand the failure
        health_detail = Ceph(client).health(detail=True)
        log.error(f"Cluster health detail: {health_detail}")
        
        # Convert health_detail to string for checking
        health_detail_str = str(health_detail).lower()
        
        # Check if the health issue is related to node-exporter
        if "node-exporter" in health_detail_str or "node_exporter" in health_detail_str:
            log.info("Health issue related to node-exporter detected. Attempting to redeploy all node-exporter daemons.")
            try:
                # Get all node-exporter daemons
                node_exporter_daemons = CephAdm(node).ceph.orch.ps(
                    daemon_type="node-exporter", format="json"
                )
                log.info(f"Node-exporter daemons: {node_exporter_daemons}")
                
                # Redeploy node-exporter service
                log.info("Redeploying node-exporter service...")
                redeploy_out = CephAdm(node).ceph.orch.redeploy("node-exporter")
                log.info(f"Redeploy output: {redeploy_out}")
                
                # Wait for redeployment to complete and check health again
                log.info("Waiting for node-exporter redeployment to complete...")
                import time
                time.sleep(30)  # Give some time for daemons to redeploy
                
                # Check cluster health again after redeployment
                health_after_redeploy = wait_for_cluster_health(client, "HEALTH_OK", 300, 10)
                if health_after_redeploy:
                    log.info("Cluster health is now HEALTH_OK after node-exporter redeployment")
                else:
                    health_detail_after = Ceph(client).health(detail=True)
                    log.error(f"Cluster health detail after redeploy: {health_detail_after}")
                    raise StaggeredUpgradeError(
                        f"Cluster not in 'HEALTH_OK' state even after node-exporter redeployment. Health detail: {health_detail_after}"
                    )
            except Exception as e:
                log.error(f"Failed to redeploy node-exporter: {str(e)}")
                raise StaggeredUpgradeError(
                    f"Cluster not in 'HEALTH_OK' state. Health detail: {health_detail}. Failed to redeploy node-exporter: {str(e)}"
                )
        else:
            raise StaggeredUpgradeError(
                f"Cluster not in 'HEALTH_OK' state. Health detail: {health_detail}"
            )
    # Set osd flags
    for flag in osd_flags:
        if CephAdm(node).ceph.osd.set(flag):
            raise StaggeredUpgradeError("Unable to set osd flag")
    # Check target image
    if CephAdm(node).ceph.orch.upgrade.check(image=target_image):
        raise StaggeredUpgradeError("Upgrade image check failed")
    # Staggered upgrade with daemon_types
    if action == "daemon_types":
        daemon_types = config.get("daemon_types")
        if daemon_types == "osd":
            limit = config.get("limit")
            if CephAdm(node).ceph.orch.upgrade.start(
                image=target_image, daemon_types=daemon_types, limit=limit
            ):
                raise StaggeredUpgradeError("Unable to start upgrade with daemon_types")
        else:
            if CephAdm(node).ceph.orch.upgrade.start(
                image=target_image, daemon_types=daemon_types
            ):
                raise StaggeredUpgradeError("Unable to start upgrade with daemon_types")
    # Staggered upgrade with services
    if action == "services":
        services = config.get("services")
        if services == "osd.all_available_devices":
            limit = config.get("limit")
            if CephAdm(node).ceph.orch.upgrade.start(
                image=target_image, services=services, limit=limit
            ):
                raise StaggeredUpgradeError("Unable to start upgrade with services")
        else:
            if CephAdm(node).ceph.orch.upgrade.start(
                image=target_image, services=services
            ):
                raise StaggeredUpgradeError("Unable to start upgrade with services")
    # Staggered upgrade with hosts
    if action == "hosts":
        nodes = config.get("nodes")
        hosts = ",".join(
            [ceph_cluster.get_nodes()[int(node[-1])].hostname for node in nodes]
        )
        if CephAdm(node).ceph.orch.upgrade.start(image=target_image, hosts=hosts):
            raise StaggeredUpgradeError("Unable to start upgrade with hosts")
    # Staggered upgrade with all combinations
    if action == "all_combination":
        nodes = config.get("nodes")
        daemon_types = config.get("daemon_types")
        limit = config.get("limit")
        services = config.get("services")
        hosts = ",".join(
            [ceph_cluster.get_nodes()[int(node[-1])].hostname for node in nodes]
        )
        if CephAdm(node).ceph.orch.upgrade.start(
            image=target_image, daemon_types=daemon_types, limit=limit, hosts=hosts
        ):
            raise StaggeredUpgradeError("Unable to start upgrade with all combinations")
    # Check upgrade status
    orch.monitor_upgrade_status()
    # Unset osd flags
    for flag in osd_flags:
        if CephAdm(node).ceph.osd.unset(flag):
            raise StaggeredUpgradeError("Unable to set osd flag")
    # Check cluster health after upgrade
    health = wait_for_cluster_health(client, "HEALTH_OK", 300, 10)
    if not health:
        raise StaggeredUpgradeError("Cluster not in 'HEALTH_OK' state")
    return 0
