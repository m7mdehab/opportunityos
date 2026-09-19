param name string
param managedEnvironmentId string
param image string
param registryServer string
param registryUsername string
@secure()
param registryPassword string
param role string
param externalIngress bool
param targetPort int = 8000
param minReplicas int
param maxReplicas int
@secure()
param cloudDatabaseUrl string
@secure()
param truthPackUri string = ''
@secure()
param truthPackAuthToken string = ''
@secure()
param truthPackApiKey string = ''
param truthPackHash string = ''
@secure()
param founderPasswordHash string = ''
@secure()
param sessionSecret string = ''
param publicOrigin string = ''

var isApi = role == 'api'
var isWorker = role == 'worker'
var isScheduler = role == 'scheduler'

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: resourceGroup().location
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: union({
      secrets: concat([
        { name: 'cloud-database-url'; value: cloudDatabaseUrl }
        { name: 'registry-password'; value: registryPassword }
      ], (isApi || isWorker) ? [
        { name: 'truth-pack-uri'; value: truthPackUri }
        { name: 'truth-pack-auth-token'; value: truthPackAuthToken }
        { name: 'truth-pack-api-key'; value: truthPackApiKey }
      ] : [], isApi ? [
        { name: 'founder-password-hash'; value: founderPasswordHash }
        { name: 'session-secret'; value: sessionSecret }
      ] : [])
    }, {
      registries: [
        {
          server: registryServer
          username: registryUsername
          passwordSecretRef: 'registry-password'
        }
      ]
    }, externalIngress ? {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
      }
    } : {})
    template: {
      containers: [
        {
          name: role
          image: image
          command: [ 'python', 'scripts/container_entrypoint.py', role ]
          env: concat([
            { name: 'CLOUD_DATABASE_URL'; secretRef: 'cloud-database-url' }
            { name: 'OPPORTUNITYOS_ENVIRONMENT'; value: 'cloud' }
          ], isApi ? [
            { name: 'OPPORTUNITYOS_FOUNDER_PASSWORD_HASH'; secretRef: 'founder-password-hash' }
            { name: 'OPPORTUNITYOS_SESSION_SECRET'; secretRef: 'session-secret' }
            { name: 'OPPORTUNITYOS_PUBLIC_ORIGIN'; value: publicOrigin }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_URI'; secretRef: 'truth-pack-uri' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN'; secretRef: 'truth-pack-auth-token' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_API_KEY'; secretRef: 'truth-pack-api-key' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_HASH'; value: truthPackHash }
            { name: 'OPPORTUNITYOS_FORCE_SECURE_COOKIES'; value: '1' }
          ] : isWorker ? [
            { name: 'OPPORTUNITYOS_TRUTH_PACK_URI'; secretRef: 'truth-pack-uri' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_AUTH_TOKEN'; secretRef: 'truth-pack-auth-token' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_API_KEY'; secretRef: 'truth-pack-api-key' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_HASH'; value: truthPackHash }
          ] : [])
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}
