/*
    Script that trigger testsuite for upstream recipe 
*/
// Global variables section
def nodeName = "centos-7"
def sharedLib
def testStages = [:]
def testResults = [:]
def upstreamVersion = "quincy"

// Pipeline script entry point
node(nodeName) {
    try {
        timeout(unit: "MINUTES", time: 30) {
            stage('Preparing') {
                if (env.WORKSPACE) { sh script: "sudo rm -rf * .venv" }
                checkout(
                    scm: [
                        $class: 'GitSCM',
                        branches: [[name: 'refs/remotes/origin/test_upstream']],
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
            def location="/ceph/cephci-jenkins/latest-rhceph-container-info/upstream.yaml"
            def yamlFileExists = sh (returnStatus: true, script: "ls -l ${location}")
            if (yamlFileExists != 0) {
                println "File ${location} does not exist."
                return [:]
            }
            def dataContent = readYaml file: "${location}"
            println "content of release file is: ${dataContent}"
        }
        stage('Execute Testsuites') {
            testStages = sharedLib.fetchStagesUpstream(upstreamVersion, testResults)
            if ( testStages.isEmpty() ) {
                currentBuild.result = "ABORTED"
                error "No test scripts were found for execution."
            }
            println "upstream script ${testStages} does not exist."
        }
        stage('publish result') {
            if ( ! ("FAIL" in sharedLib.fetchStageStatus(testResults)) ) {
                def location="/ceph/cephci-jenkins/latest-rhceph-container-info/upstream.yaml"
                def latestContent = sharedLib.readFromReleaseFileforUpstraem()
                if ( latestContent.containsKey(upstreamVersion) ) {
                    latestContent[upstreamVersion] = dataContent[upstreamVersion]  // need to update
                }
                else {
                    def updateContent = ["${upstreamVersion}": dataContent[upstreamVersion]]   // need to update
                    latestContent += updateContent
                }
            }
            writeYaml file: "${location}", data: latestContent, overwrite: true
            def updatedDataContent = readYaml file: "${location}"
            println "updated content of release file is: ${updatedDataContent}"
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
