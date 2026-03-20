/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	servingv1alpha1 "github.com/KyleKichulYun/Lightweight-AI-Model-Serving-Router/operator/api/v1alpha1"
)

// ModelAutoscalerReconciler reconciles a ModelAutoscaler object
type ModelAutoscalerReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=serving.kyle.io,resources=modelautoscalers,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=serving.kyle.io,resources=modelautoscalers/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=serving.kyle.io,resources=modelautoscalers/finalizers,verbs=update
// [수정] Operator가 Deployment 리소스를 조회하고 업데이트할 수 있도록 RBAC 권한 추가
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;update;patch

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
// TODO(user): Modify the Reconcile function to compare the state specified by
// the ModelAutoscaler object against the actual cluster state, and then
// perform operations to make the cluster state reflect the state specified by
// the user.
//
// For more details, check Reconcile and its Result here:
// - https://pkg.go.dev/sigs.k8s.io/controller-runtime@v0.23.1/pkg/reconcile
func (r *ModelAutoscalerReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	_ = logf.FromContext(ctx)

	// TODO(user): your logic here
	// logger 변수를 활성화하여 로그 출력에 사용
	logger := logf.FromContext(ctx)
	// 1. 우리가 정의한 Custom Resource(CR) 가져오기
	var autoscaler servingv1alpha1.ModelAutoscaler
	if err := r.Get(ctx, req.NamespacedName, &autoscaler); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	// 2. Go 라우터의 메트릭 API 호출
	resp, err := http.Get(autoscaler.Spec.MetricsURL)
	if err != nil {
		logger.Error(err, "메트릭을 가져오지 못했습니다.")
		return ctrl.Result{RequeueAfter: time.Second * 5}, nil // 5초 뒤 재시도
	}
	defer resp.Body.Close()

	var metrics struct {
		ActiveRequests int `json:"active_requests"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&metrics); err != nil {
		return ctrl.Result{RequeueAfter: time.Second * 5}, nil
	}

	// 3. 타겟 Deployment(Python AI 모델) 가져오기
	var deploy appsv1.Deployment
	if err := r.Get(ctx, types.NamespacedName{Name: autoscaler.Spec.TargetDeployment, Namespace: req.Namespace}, &deploy); err != nil {
		logger.Error(err, "Target Deployment를 찾을 수 없습니다.")
		return ctrl.Result{RequeueAfter: time.Second * 5}, nil
	}

	// 4. 오토스케일링 수학 로직 (필요한 파드 수 계산)
	var currentReplicas int32 = 0
	if deploy.Spec.Replicas != nil {
		currentReplicas = *deploy.Spec.Replicas
	}

	desiredReplicas := int32(math.Ceil(float64(metrics.ActiveRequests) / float64(autoscaler.Spec.TargetRequestsPerPod)))

	if desiredReplicas < autoscaler.Spec.MinReplicas {
		desiredReplicas = autoscaler.Spec.MinReplicas
	}
	if desiredReplicas > autoscaler.Spec.MaxReplicas {
		desiredReplicas = autoscaler.Spec.MaxReplicas
	}

	// 5. 스케일링 실행 (현재 개수와 다를 때만)
	if desiredReplicas != currentReplicas {
		logger.Info(fmt.Sprintf("🚨 부하 감지! 스케일링 수행: %d -> %d (현재 활성 요청: %d)", currentReplicas, desiredReplicas, metrics.ActiveRequests))
		deploy.Spec.Replicas = &desiredReplicas
		if err := r.Update(ctx, &deploy); err != nil {
			return ctrl.Result{}, err
		}
	} else {
		logger.Info(fmt.Sprintf("✅ 안정 상태. 현재 파드: %d, 활성 요청: %d", currentReplicas, metrics.ActiveRequests))
	}

	// 6. 5초마다 이 루프를 무한 반복 (Polling)
	return ctrl.Result{RequeueAfter: time.Second * 5}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *ModelAutoscalerReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&servingv1alpha1.ModelAutoscaler{}).
		Named("modelautoscaler").
		Complete(r)
}
