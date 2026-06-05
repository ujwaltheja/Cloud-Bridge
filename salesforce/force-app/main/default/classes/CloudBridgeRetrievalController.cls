public with sharing class CloudBridgeRetrievalController {
    @AuraEnabled(cacheable=true)
    public static Map<String, String> getDefaults() {
        return new Map<String, String>{
            'backendBaseUrl' => CloudBridgeApiService.getBaseUrl(),
            'defaultOrgId' => Label.CloudBridge_Default_Org_Id
        };
    }

    @AuraEnabled
    public static Map<String, Object> createRetrievalJob(String packageXml, String orgId, Boolean useBackground, String deploymentRequester) {
        if (String.isBlank(packageXml)) {
            throw new AuraHandledException('package.xml content is required.');
        }

        String orgIdToUse = String.isBlank(orgId) ? Label.CloudBridge_Default_Org_Id : orgId;
        if (String.isBlank(orgIdToUse)) {
            throw new AuraHandledException('org_id is required. Provide it in the LWC or set CloudBridge_Default_Org_Id label.');
        }

        Boolean background = (useBackground == null) ? true : useBackground;

        Map<String, Object> payload = new Map<String, Object>{
            'org_id' => orgIdToUse,
            'package_xml' => packageXml
        };
        if (!String.isBlank(deploymentRequester)) {
            payload.put('description', 'Deployment requester: ' + deploymentRequester.trim());
        }

        HttpResponse res = CloudBridgeApiService.send(
            'POST',
            '/api/v1/retrievals?use_background=' + String.valueOf(background),
            payload
        );
        CloudBridgeApiService.throwIfNotOk(res);

        Map<String, Object> job = CloudBridgeApiService.parseJsonBody(res);
        if (job.containsKey('id')) {
            String jobId = String.valueOf(job.get('id'));
            job.put('download_sfdx_url', CloudBridgeApiService.buildEndpoint('/api/v1/retrievals/' + jobId + '/download?format=sfdx'));
            job.put('download_json_url', CloudBridgeApiService.buildEndpoint('/api/v1/retrievals/' + jobId + '/download?format=json'));
        }
        return job;
    }

    @AuraEnabled(cacheable=false)
    public static Map<String, Object> getRetrievalJob(String jobId) {
        if (String.isBlank(jobId)) {
            throw new AuraHandledException('jobId is required.');
        }

        HttpResponse res = CloudBridgeApiService.send('GET', '/api/v1/retrievals/' + jobId, null);
        CloudBridgeApiService.throwIfNotOk(res);

        Map<String, Object> job = CloudBridgeApiService.parseJsonBody(res);
        String idValue = String.valueOf(job.get('id'));
        if (!String.isBlank(idValue)) {
            job.put('download_sfdx_url', CloudBridgeApiService.buildEndpoint('/api/v1/retrievals/' + idValue + '/download?format=sfdx'));
            job.put('download_json_url', CloudBridgeApiService.buildEndpoint('/api/v1/retrievals/' + idValue + '/download?format=json'));
        }
        return job;
    }

    @AuraEnabled(cacheable=false)
    public static List<Object> listRecentRetrievalJobs(Integer limitSize) {
        Integer safeLimit = (limitSize == null || limitSize <= 0 || limitSize > 50) ? 10 : limitSize;

        HttpResponse res = CloudBridgeApiService.send('GET', '/api/v1/retrievals', null);
        CloudBridgeApiService.throwIfNotOk(res);

        Object parsed = JSON.deserializeUntyped(res.getBody());
        if (!(parsed instanceof List<Object>)) {
            return new List<Object>();
        }

        List<Object> rows = (List<Object>) parsed;

        List<Object> limited = new List<Object>();
        Integer count = 0;
        for (Object item : rows) {
            limited.add(item);
            count++;
            if (count >= safeLimit) {
                break;
            }
        }

        return limited;
    }
}
