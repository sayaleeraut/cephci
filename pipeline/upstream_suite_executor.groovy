/*
    Script that trigger testsuite for upstream build
*/
// Global variables section
def nodeName = "centos-7"
def sharedLib
def testStages = [:]
def testResults = [:]
def upstreamVersion = "quincy"
def buildType = "upstream"
def overrides = [:]

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
                sharedLib = load("${env.WORKSPACE}/pipeline/vars/v3.groovy")
                sharedLib.prepareNode()
            }
        }
        stage('Execute Testsuites') {
            overrides.build = upstreamVersion
            def tags = "${buildType}, stage-1"
            print("Fetching stages")
            fetchStages = sharedLib.fetchStagesUpstream(tags, overrides, testResults, upstreamVersion)
            print("Stages fetched: ${fetchStages}")
            testStages = fetchStages["testStages"]
            if ( testStages.isEmpty() ) {
                currentBuild.result = "ABORTED"
                error "No test scripts were found for execution."
            }
            final_stage = fetchStages["final_stage"]
            println("final_stage : ${final_stage}")
            currentBuild.description = "${buildType} - ${upstreamVersion}"
        }

        parallel testStages

        stage('publish result') {
            if ( ! ("FAIL" in sharedLib.fetchStageStatus(testResults)) ) {
                println "Publish result"
            }
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
