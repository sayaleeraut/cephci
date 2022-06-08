/*
    Script that trigger testsuite for upstream recipe 
*/
// Global variables section
def nodeName = "centos-7"
def sharedLib

// Pipeline script entry point
node(nodeName) {
    try {
        timeout(unit: "MINUTES", time: 30) {
            stage('Preparing') {
                if (env.WORKSPACE) { sh script: "sudo rm -rf * .venv" }
                checkout(
                    scm: [
                        $class: 'GitSCM',
                        branches: [[name: 'origin/master']],
                        extensions: [
                            [
                                $class: 'CleanBeforeCheckout',
                                deleteUntrackedNestedRepositories: true
                            ],
                            [
                                $class: 'WipeWorkspace'
                            ],
                            [
                                $class: 'CloneOption',
                                depth: 1,
                                noTags: true,
                                shallow: true,
                                timeout: 10,
                                reference: ''
                            ]
                        ],
                        userRemoteConfigs: [[
                            url: 'https://github.com/red-hat-storage/cephci.git'
                        ]]
                    ],
                    changelog: false,
                    poll: false
                )
                sharedLib = load("${env.WORKSPACE}/pipeline/vars/lib.groovy")
                sharedLib.prepareNode()
            }
        }

        stage('Get recipe Details') {
          upstreamVersion = "quincy"
          def location="/ceph/cephci-jenkins/latest-rhceph-container-info/upstream.yaml"
          def yamlFileExists = sh (returnStatus: true, script: "ls -l ${location}")
          if (yamlFileExists != 0) {
            println "File ${location}/${yamlFile} does not exist."
            return [:]
          }
          def datacontent = readYaml file: "${location}"
          println "content of release file is: ${dataContent}"
        }
    } catch(Exception err) {
        if (currentBuild.result != "ABORTED") {
            // notify about failure
            currentBuild.result = "FAILURE"
            def failureReason = err.getMessage()
            echo failureReason
        }
    }
}
