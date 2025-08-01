import secrets
import string
import traceback
from datetime import datetime, timedelta

from ceph.parallel import parallel
from ceph.utils import check_ceph_healthly
from tests.cephfs.cephfs_utilsV1 import FsUtils as FsUtilsV1
from utility.log import Log

log = Log(__name__)

global stop_flag


def start_io_time(fs_util, client1, mounting_dir, timeout=300):
    global stop_flag
    stop_flag = False
    iter = 0
    if timeout:
        stop = datetime.now() + timedelta(seconds=timeout)
    else:
        stop = 0
    while True:
        if stop and datetime.now() > stop:
            log.info("Timed out *************************")
            break
        mount_type = "fuse" if "fuse" in mounting_dir else "kernel"
        client1.exec_command(
            sudo=True,
            cmd=f"mkdir -p {mounting_dir}/{mount_type}_{__name__}_run_ios_{iter}",
        )
        fs_util.run_ios(
            client1,
            f"{mounting_dir}/{mount_type}_{__name__}_run_ios_{iter}",
            io_tools=["smallfile"],
        )
        iter = iter + 1
        if stop_flag:
            break


def run(ceph_cluster, **kw):
    """
    CEPH-11263 - MDS node power failure, with client IO

    Test Steps:
    1. Mount Fuse and Kernel mounts
    2. Run IOs and perform mds power off parallel
    3. Do this on all the mds nodes in serial fashion
    Args:
        ceph_cluster:
        **kw:

    Returns:

    """
    try:
        test_data = kw.get("test_data")
        fs_util_v1 = FsUtilsV1(ceph_cluster, test_data=test_data)
        erasure = (
            FsUtilsV1.get_custom_config_value(test_data, "erasure")
            if test_data
            else False
        )
        mds_nodes = ceph_cluster.get_ceph_objects("mds")
        clients = ceph_cluster.get_ceph_objects("client")
        config = kw.get("config")
        osp_cred = config.get("osp_cred")
        num_of_osds = config.get("mds_of_osds")
        build = config.get("build", config.get("rhbuild"))
        print(osp_cred)
        if config.get("cloud-type") == "openstack":
            os_cred = osp_cred.get("globals").get("openstack-credentials")
            params = {}
            params["username"] = os_cred["username"]
            params["password"] = os_cred["password"]
            params["auth_url"] = os_cred["auth-url"]
            params["auth_version"] = os_cred["auth-version"]
            params["tenant_name"] = os_cred["tenant-name"]
            params["service_region"] = os_cred["service-region"]
            params["domain_name"] = os_cred["domain"]
            params["tenant_domain_id"] = os_cred["tenant-domain-id"]
            params["cloud_type"] = "openstack"
        elif config.get("cloud-type") == "ibmc":
            pass
        else:
            pass

        fs_util_v1.prepare_clients(clients, build)
        fs_util_v1.auth_list(clients)
        fs_name = "cephfs" if not erasure else "cephfs-ec"
        fs_details = fs_util_v1.get_fs_info(clients[0], fs_name)

        if not fs_details:
            fs_util_v1.create_fs(clients[0], fs_name)
        host_list = [mdsnode.node.hostname for mdsnode in mds_nodes]
        hosts = " ".join(host_list)
        clients[0].exec_command(
            sudo=True,
            cmd=f"ceph orch apply mds {fs_name} --placement='3 {hosts}'",
        )

        mon_node_ip = fs_util_v1.get_mon_node_ips()
        mon_node_ip = ",".join(mon_node_ip)
        kernel_mount_dir = "/mnt/kernel_" + "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for i in range(5)
        )
        fs_util_v1.kernel_mount(
            [clients[0]],
            kernel_mount_dir,
            mon_node_ip,
            new_client_hostname="admin",
            extra_params=f",fs={fs_name}",
        )
        fuse_mount_dir = "/mnt/fuse_" + "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for i in range(5)
        )

        fs_util_v1.fuse_mount(
            [clients[0]],
            fuse_mount_dir,
            new_client_hostname="admin",
            extra_params=f" --client_fs {fs_name}",
        )
        with parallel() as p:
            p.spawn(
                start_io_time,
                fs_util_v1,
                clients[0],
                fuse_mount_dir,
                timeout=900,
            )
            p.spawn(
                start_io_time,
                fs_util_v1,
                clients[0],
                kernel_mount_dir,
            )
            global stop_flag
            for mds in mds_nodes:
                cluster_health_beforeIO = check_ceph_healthly(
                    clients[0],
                    num_of_osds,
                    len(mds_nodes),
                    build,
                    None,
                    300,
                )
                fs_util_v1.node_power_failure(node=mds.node, sleep_time=120, **params)
                cluster_health_afterIO = check_ceph_healthly(
                    clients[0],
                    num_of_osds,
                    len(mds_nodes),
                    build,
                    None,
                    300,
                )
                if cluster_health_afterIO == cluster_health_beforeIO:
                    log.info("cluster is healthy")
                else:
                    log.error("cluster is not healty")
            log.info("Setting stop flag")
            stop_flag = True
        return 0

    except Exception as e:
        log.error(e)
        log.error(traceback.format_exc())
        return 1
    finally:
        log.info("Cleaning up the system")
        fs_util_v1.client_clean_up(
            "umount", fuse_clients=[clients[0]], mounting_dir=fuse_mount_dir
        )
        fs_util_v1.client_clean_up(
            "umount",
            kernel_clients=[clients[0]],
            mounting_dir=kernel_mount_dir,
        )
